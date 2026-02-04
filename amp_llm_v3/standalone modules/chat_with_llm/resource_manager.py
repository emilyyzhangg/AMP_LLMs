"""
Resource Manager for LLM Services
==================================

Manages system resources to prevent memory exhaustion:
- Checks available memory before starting LLM jobs
- Queues jobs when memory is insufficient
- Automatically starts queued jobs when memory clears
- Rate limits API calls to prevent hitting external limits

Configuration (via .env):
- MEMORY_MIN_FREE_GB: Minimum free RAM required (default: 6)
- MAX_CONCURRENT_LLM_JOBS: Maximum simultaneous LLM jobs (default: 2)
- NCT_MAX_CONCURRENT_REQUESTS: Max concurrent NCT API calls (default: 3)
- NCT_RATE_LIMIT_PER_SECOND: API calls per second limit (default: 2)
"""

import os
import asyncio
import logging
import time
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
from collections import deque

# Try to import psutil for memory monitoring
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    logging.warning("psutil not installed - memory monitoring disabled. Install with: pip install psutil")

from dotenv import load_dotenv

# Load .env from current dir and parent
load_dotenv()
_script_dir = Path(__file__).parent.resolve()
_root_env = _script_dir.parent.parent / ".env"
if _root_env.exists():
    load_dotenv(_root_env)

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

# Memory thresholds (in GB)
MEMORY_MIN_FREE_GB = float(os.getenv("MEMORY_MIN_FREE_GB", "6"))

# Concurrency limits
MAX_CONCURRENT_LLM_JOBS = int(os.getenv("MAX_CONCURRENT_LLM_JOBS", "2"))
NCT_MAX_CONCURRENT_REQUESTS = int(os.getenv("NCT_MAX_CONCURRENT_REQUESTS", "3"))
NCT_RATE_LIMIT_PER_SECOND = float(os.getenv("NCT_RATE_LIMIT_PER_SECOND", "2"))


# =============================================================================
# Queue Status
# =============================================================================

class QueueStatus(str, Enum):
    QUEUED = "queued"
    WAITING_MEMORY = "waiting_memory"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class QueuedJob:
    """A job waiting in the resource queue."""
    job_id: str
    job_type: str  # 'llm_annotation', 'nct_lookup', etc.
    priority: int = 0  # Higher = more priority
    memory_required_gb: float = 6.0
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    status: QueueStatus = QueueStatus.QUEUED
    queue_position: int = 0
    callback: Optional[Callable] = None  # Called when job can start
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Memory Monitor
# =============================================================================

class MemoryMonitor:
    """Monitors system memory availability."""

    @staticmethod
    def get_available_memory_gb() -> float:
        """Get available system memory in GB."""
        if not HAS_PSUTIL:
            # If psutil not available, assume we have enough memory
            logger.warning("psutil not available - assuming sufficient memory")
            return 999.0

        try:
            mem = psutil.virtual_memory()
            available_gb = mem.available / (1024 ** 3)
            return round(available_gb, 2)
        except Exception as e:
            logger.error(f"Error getting memory info: {e}")
            return 999.0  # Assume available if we can't check

    @staticmethod
    def get_memory_info() -> Dict[str, Any]:
        """Get detailed memory information."""
        if not HAS_PSUTIL:
            return {
                "available": True,
                "error": "psutil not installed"
            }

        try:
            mem = psutil.virtual_memory()
            return {
                "total_gb": round(mem.total / (1024 ** 3), 2),
                "available_gb": round(mem.available / (1024 ** 3), 2),
                "used_gb": round(mem.used / (1024 ** 3), 2),
                "percent_used": mem.percent,
                "min_required_gb": MEMORY_MIN_FREE_GB,
                "sufficient": mem.available / (1024 ** 3) >= MEMORY_MIN_FREE_GB
            }
        except Exception as e:
            return {
                "error": str(e),
                "sufficient": True  # Assume sufficient if we can't check
            }

    @staticmethod
    def has_sufficient_memory(required_gb: float = None) -> bool:
        """Check if there's enough free memory."""
        required = required_gb or MEMORY_MIN_FREE_GB
        available = MemoryMonitor.get_available_memory_gb()
        return available >= required


# =============================================================================
# Rate Limiter for API Calls
# =============================================================================

class RateLimiter:
    """Token bucket rate limiter for API calls."""

    def __init__(self, rate_per_second: float = 2.0, burst_size: int = 5):
        self.rate = rate_per_second
        self.burst_size = burst_size
        self.tokens = burst_size
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Wait until a token is available."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.burst_size, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens < 1:
                wait_time = (1 - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
                self.tokens = 0
            else:
                self.tokens -= 1


class ConcurrencySemaphore:
    """Semaphore for limiting concurrent operations."""

    def __init__(self, max_concurrent: int):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active = 0
        self._lock = asyncio.Lock()

    async def acquire(self):
        await self._semaphore.acquire()
        async with self._lock:
            self._active += 1

    async def release(self):
        async with self._lock:
            self._active -= 1
        self._semaphore.release()

    @property
    def active_count(self) -> int:
        return self._active

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, *args):
        await self.release()


# =============================================================================
# Resource Manager (Singleton)
# =============================================================================

class ResourceManager:
    """
    Central resource manager for LLM services.

    Manages:
    - Memory-based job queuing
    - Concurrent LLM job limits
    - NCT API rate limiting
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self.memory_monitor = MemoryMonitor()

        # Job queue
        self.job_queue: deque[QueuedJob] = deque()
        self.running_jobs: Dict[str, QueuedJob] = {}
        self._queue_lock = asyncio.Lock()

        # LLM concurrency control
        self.llm_semaphore = ConcurrencySemaphore(MAX_CONCURRENT_LLM_JOBS)

        # NCT API rate limiting
        self.nct_rate_limiter = RateLimiter(
            rate_per_second=NCT_RATE_LIMIT_PER_SECOND,
            burst_size=NCT_MAX_CONCURRENT_REQUESTS
        )
        self.nct_semaphore = ConcurrencySemaphore(NCT_MAX_CONCURRENT_REQUESTS)

        # Background task for processing queue
        self._queue_processor_task = None

        logger.info(f"📊 ResourceManager initialized:")
        logger.info(f"   - Min free memory: {MEMORY_MIN_FREE_GB} GB")
        logger.info(f"   - Max concurrent LLM jobs: {MAX_CONCURRENT_LLM_JOBS}")
        logger.info(f"   - NCT rate limit: {NCT_RATE_LIMIT_PER_SECOND}/s, max concurrent: {NCT_MAX_CONCURRENT_REQUESTS}")

    def start_queue_processor(self):
        """Start the background queue processor."""
        if self._queue_processor_task is None or self._queue_processor_task.done():
            self._queue_processor_task = asyncio.create_task(self._process_queue())
            logger.info("🚀 Queue processor started")

    async def _process_queue(self):
        """Background task that processes the job queue."""
        while True:
            try:
                await asyncio.sleep(2)  # Check every 2 seconds

                async with self._queue_lock:
                    if not self.job_queue:
                        continue

                    # Check if we can start the next job
                    job = self.job_queue[0]

                    # Check memory
                    if not self.memory_monitor.has_sufficient_memory(job.memory_required_gb):
                        job.status = QueueStatus.WAITING_MEMORY
                        continue

                    # Check concurrency
                    if self.llm_semaphore.active_count >= MAX_CONCURRENT_LLM_JOBS:
                        continue

                    # Start the job
                    job = self.job_queue.popleft()
                    job.status = QueueStatus.RUNNING
                    job.started_at = datetime.now()
                    self.running_jobs[job.job_id] = job

                    # Update queue positions
                    for i, queued_job in enumerate(self.job_queue):
                        queued_job.queue_position = i + 1

                    logger.info(f"🚀 Starting queued job {job.job_id}")

                    # Call the callback if provided
                    if job.callback:
                        try:
                            asyncio.create_task(job.callback())
                        except Exception as e:
                            logger.error(f"Job callback error: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Queue processor error: {e}")

    async def request_llm_slot(
        self,
        job_id: str,
        memory_required_gb: float = None,
        metadata: Dict = None
    ) -> Dict[str, Any]:
        """
        Request a slot for an LLM job.

        Returns immediately with either:
        - {"granted": True} - Job can start now
        - {"granted": False, "queue_position": N, "reason": "..."} - Job is queued
        """
        required_memory = memory_required_gb or MEMORY_MIN_FREE_GB

        # Check current memory
        mem_info = self.memory_monitor.get_memory_info()

        # Check if we can start immediately
        can_start = (
            mem_info.get("sufficient", True) and
            self.llm_semaphore.active_count < MAX_CONCURRENT_LLM_JOBS
        )

        if can_start:
            await self.llm_semaphore.acquire()
            self.running_jobs[job_id] = QueuedJob(
                job_id=job_id,
                job_type="llm_annotation",
                memory_required_gb=required_memory,
                status=QueueStatus.RUNNING,
                started_at=datetime.now(),
                metadata=metadata or {}
            )
            logger.info(f"✅ LLM slot granted for job {job_id}")
            return {
                "granted": True,
                "memory_info": mem_info,
                "active_jobs": self.llm_semaphore.active_count
            }

        # Queue the job
        async with self._queue_lock:
            job = QueuedJob(
                job_id=job_id,
                job_type="llm_annotation",
                memory_required_gb=required_memory,
                queue_position=len(self.job_queue) + 1,
                metadata=metadata or {}
            )

            if not mem_info.get("sufficient", True):
                job.status = QueueStatus.WAITING_MEMORY

            self.job_queue.append(job)

            reason = (
                f"Insufficient memory ({mem_info.get('available_gb', '?')}GB available, {required_memory}GB required)"
                if not mem_info.get("sufficient", True)
                else f"Max concurrent jobs reached ({MAX_CONCURRENT_LLM_JOBS})"
            )

            logger.info(f"⏳ Job {job_id} queued at position {job.queue_position}: {reason}")

            return {
                "granted": False,
                "queued": True,
                "queue_position": job.queue_position,
                "reason": reason,
                "memory_info": mem_info,
                "active_jobs": self.llm_semaphore.active_count
            }

    async def release_llm_slot(self, job_id: str):
        """Release an LLM slot when job completes."""
        if job_id in self.running_jobs:
            del self.running_jobs[job_id]
            await self.llm_semaphore.release()
            logger.info(f"🔓 LLM slot released for job {job_id}")

    async def cancel_queued_job(self, job_id: str) -> bool:
        """Cancel a queued job."""
        async with self._queue_lock:
            for i, job in enumerate(self.job_queue):
                if job.job_id == job_id:
                    self.job_queue.remove(job)
                    # Update positions
                    for j, remaining_job in enumerate(self.job_queue):
                        remaining_job.queue_position = j + 1
                    logger.info(f"❌ Cancelled queued job {job_id}")
                    return True
        return False

    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status."""
        mem_info = self.memory_monitor.get_memory_info()

        return {
            "memory": mem_info,
            "running_jobs": len(self.running_jobs),
            "queued_jobs": len(self.job_queue),
            "max_concurrent": MAX_CONCURRENT_LLM_JOBS,
            "queue": [
                {
                    "job_id": job.job_id,
                    "position": job.queue_position,
                    "status": job.status.value,
                    "waiting_since": job.created_at.isoformat(),
                    "metadata": job.metadata
                }
                for job in self.job_queue
            ],
            "running": [
                {
                    "job_id": job.job_id,
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "metadata": job.metadata
                }
                for job in self.running_jobs.values()
            ]
        }

    # =========================================================================
    # NCT API Rate Limiting
    # =========================================================================

    async def acquire_nct_slot(self):
        """Acquire a slot for NCT API call (rate limited)."""
        await self.nct_rate_limiter.acquire()
        await self.nct_semaphore.acquire()

    async def release_nct_slot(self):
        """Release NCT API slot."""
        await self.nct_semaphore.release()

    def nct_rate_limited(self):
        """Context manager for NCT API calls."""
        return NCTRateLimitedContext(self)


class NCTRateLimitedContext:
    """Async context manager for rate-limited NCT API calls."""

    def __init__(self, manager: ResourceManager):
        self.manager = manager

    async def __aenter__(self):
        await self.manager.acquire_nct_slot()
        return self

    async def __aexit__(self, *args):
        await self.manager.release_nct_slot()


# =============================================================================
# Singleton Instance
# =============================================================================

def get_resource_manager() -> ResourceManager:
    """Get the singleton ResourceManager instance."""
    return ResourceManager()
