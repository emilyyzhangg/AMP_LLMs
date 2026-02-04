"""
CSV Annotation Job Manager
Handles background processing of CSV annotation jobs to avoid Cloudflare 524 timeouts.

Add this to your chat_api.py or import it.
"""
import asyncio
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

# Job retention time in seconds (default: 3 hours)
# Jobs older than this will be automatically cleaned up
JOB_RETENTION_SECONDS = 3 * 60 * 60  # 3 hours

# How often to check for expired jobs (in seconds)
CLEANUP_INTERVAL_SECONDS = 300  # 5 minutes


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AnnotationJob:
    job_id: str
    status: JobStatus = JobStatus.PENDING
    progress: str = "Queued"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    total_trials: int = 0
    processed_trials: int = 0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class CSVJobManager:
    """
    Manages background CSV annotation jobs.
    
    Usage:
        job_manager = CSVJobManager()
        
        # In your endpoint:
        job_id = await job_manager.create_job(nct_ids, model, ...)
        return {"job_id": job_id}  # Returns immediately!
        
        # Status endpoint:
        status = job_manager.get_job_status(job_id)
    """
    
    def __init__(self):
        self.jobs: Dict[str, AnnotationJob] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
    
    def start_cleanup_task(self):
        """Start background task to clean up old jobs (call on app startup)"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_old_jobs())
    
    async def _cleanup_old_jobs(self):
        """Remove jobs older than JOB_RETENTION_SECONDS (default: 3 hours)"""
        while True:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            now = datetime.now()
            expired = [
                job_id for job_id, job in self.jobs.items()
                if (now - job.created_at).total_seconds() > JOB_RETENTION_SECONDS
            ]
            for job_id in expired:
                del self.jobs[job_id]
                logger.info(f"🧹 Cleaned up expired job: {job_id}")
    
    async def create_job(
        self,
        nct_ids: list,
        model: str,
        temperature: float,
        process_func,  # async function to process a single NCT ID
        on_complete=None  # callback when job completes
    ) -> str:
        """
        Create and start a background annotation job.
        
        Args:
            nct_ids: List of NCT IDs to process
            model: Model name for annotation
            temperature: LLM temperature
            process_func: Async function(nct_id, model, temperature) -> annotation
            on_complete: Optional callback(job_id, results) when done
        
        Returns:
            job_id: Use this to poll status
        """
        job_id = str(uuid.uuid4())
        
        job = AnnotationJob(
            job_id=job_id,
            status=JobStatus.PENDING,
            total_trials=len(nct_ids),
            progress=f"Starting annotation of {len(nct_ids)} trials..."
        )
        self.jobs[job_id] = job
        
        # Start background processing
        asyncio.create_task(
            self._process_job(job_id, nct_ids, model, temperature, process_func, on_complete)
        )
        
        logger.info(f"📋 Created job {job_id} for {len(nct_ids)} NCT IDs")
        return job_id
    
    async def _process_job(
        self,
        job_id: str,
        nct_ids: list,
        model: str,
        temperature: float,
        process_func,
        on_complete
    ):
        """Background worker for processing annotations"""
        job = self.jobs.get(job_id)
        if not job:
            return
        
        job.status = JobStatus.PROCESSING
        job.updated_at = datetime.now()
        
        results = []
        errors = []
        start_time = datetime.now()
        
        try:
            for i, nct_id in enumerate(nct_ids):
                job.processed_trials = i
                job.progress = f"Processing {i + 1}/{len(nct_ids)}: {nct_id}"
                job.updated_at = datetime.now()
                
                logger.info(f"📝 Job {job_id}: Processing {nct_id} ({i + 1}/{len(nct_ids)})")
                
                try:
                    annotation = await process_func(nct_id, model, temperature)
                    results.append({
                        "nct_id": nct_id,
                        "annotation": annotation,
                        "success": True
                    })
                except Exception as e:
                    logger.error(f"❌ Job {job_id}: Failed to annotate {nct_id}: {e}")
                    errors.append({
                        "nct_id": nct_id,
                        "error": str(e)
                    })
            
            # Job completed
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            job.status = JobStatus.COMPLETED
            job.processed_trials = len(nct_ids)
            job.progress = "Completed"
            job.result = {
                "total": len(nct_ids),
                "successful": len(results),
                "failed": len(errors),
                "results": results,
                "errors": errors,
                "total_time_seconds": round(duration, 1),
                "model": model
            }
            job.updated_at = datetime.now()
            
            logger.info(f"✅ Job {job_id} completed: {len(results)} success, {len(errors)} errors")
            
            if on_complete:
                await on_complete(job_id, job.result)
                
        except Exception as e:
            logger.error(f"❌ Job {job_id} failed: {e}")
            job.status = JobStatus.FAILED
            job.error = str(e)
            job.updated_at = datetime.now()
    
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get current status of a job"""
        job = self.jobs.get(job_id)
        
        if not job:
            return {
                "status": "not_found",
                "error": f"Job {job_id} not found"
            }
        
        response = {
            "job_id": job.job_id,
            "status": job.status.value,
            "progress": job.progress,
            "total_trials": job.total_trials,
            "processed_trials": job.processed_trials,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat()
        }
        
        if job.status == JobStatus.COMPLETED:
            response["result"] = job.result
        elif job.status == JobStatus.FAILED:
            response["error"] = job.error
        
        return response


# Global instance
job_manager = CSVJobManager()