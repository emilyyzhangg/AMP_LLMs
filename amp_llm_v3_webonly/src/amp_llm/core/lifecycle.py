"""
Application lifecycle management with proper cleanup.
FIXED: Prevents recursion errors during shutdown.
"""

import asyncio
from typing import Callable, Awaitable, List, Optional
from enum import Enum
from dataclasses import dataclass

from amp_llm.config import get_logger

logger = get_logger(__name__)


class LifecyclePhase(Enum):
    """Application lifecycle phases."""
    INITIALIZING = "initializing"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class LifecycleHook:
    """Represents a lifecycle hook."""
    name: str
    phase: LifecyclePhase
    callback: Callable[[], Awaitable[None]]
    priority: int = 0


class LifecycleManager:
    """
    Manages application lifecycle hooks.
    FIXED: Proper shutdown handling to prevent recursion.
    """
    
    def __init__(self):
        self.hooks: List[LifecycleHook] = []
        self.current_phase = LifecyclePhase.INITIALIZING
        self._shutdown_running = False  # Prevent recursive shutdowns
    
    def register_hook(
        self,
        phase: LifecyclePhase,
        callback: Callable[[], Awaitable[None]],
        name: Optional[str] = None,
        priority: int = 0,
    ) -> None:
        """Register a lifecycle hook."""
        if name is None:
            name = callback.__name__
        
        hook = LifecycleHook(
            name=name,
            phase=phase,
            callback=callback,
            priority=priority,
        )
        
        self.hooks.append(hook)
        logger.debug(f"Registered {phase.value} hook: {name} (priority={priority})")
    
    async def run_hooks(self, phase: LifecyclePhase) -> None:
        """Run all hooks for a specific phase."""
        # Get hooks for this phase
        phase_hooks = [h for h in self.hooks if h.phase == phase]
        
        # Sort by priority
        phase_hooks.sort(key=lambda h: h.priority)
        
        logger.info(f"Running {len(phase_hooks)} {phase.value} hook(s)")
        
        # Run hooks
        for hook in phase_hooks:
            try:
                logger.debug(f"Running {phase.value} hook: {hook.name}")
                
                # Run hook with timeout to prevent hanging
                await asyncio.wait_for(hook.callback(), timeout=30.0)
                
            except asyncio.TimeoutError:
                logger.error(f"Timeout in {phase.value} hook '{hook.name}'")
                if phase != LifecyclePhase.STOPPING:
                    raise
            except asyncio.CancelledError:
                logger.warning(f"Cancelled {phase.value} hook '{hook.name}'")
                if phase != LifecyclePhase.STOPPING:
                    raise
            except Exception as e:
                logger.error(f"Error in {phase.value} hook '{hook.name}': {e}", exc_info=True)
                # Don't stop on hook errors during shutdown
                if phase != LifecyclePhase.STOPPING:
                    raise
    
    async def run_startup_hooks(self) -> None:
        """Run startup hooks."""
        self.current_phase = LifecyclePhase.STARTING
        await self.run_hooks(LifecyclePhase.STARTING)
        self.current_phase = LifecyclePhase.RUNNING
    
    async def run_shutdown_hooks(self) -> None:
        """
        Run shutdown hooks with recursion prevention.
        FIXED: Prevents infinite recursion during shutdown.
        """
        if self._shutdown_running:
            logger.debug("Shutdown already in progress, skipping duplicate call")
            return
        
        try:
            self._shutdown_running = True
            self.current_phase = LifecyclePhase.STOPPING
            
            # Run shutdown hooks with overall timeout
            try:
                await asyncio.wait_for(
                    self.run_hooks(LifecyclePhase.STOPPING),
                    timeout=60.0  # 60 second total timeout for all shutdown hooks
                )
            except asyncio.TimeoutError:
                logger.error("Shutdown hooks timed out after 60 seconds")
            
            self.current_phase = LifecyclePhase.STOPPED
            
        finally:
            self._shutdown_running = False
    
    # Decorator shortcuts
    def on_startup(self, priority: int = 0):
        """Decorator to register startup hook."""
        def decorator(func: Callable[[], Awaitable[None]]):
            self.register_hook(LifecyclePhase.STARTING, func, priority=priority)
            return func
        return decorator
    
    def on_shutdown(self, priority: int = 0):
        """Decorator to register shutdown hook."""
        def decorator(func: Callable[[], Awaitable[None]]):
            self.register_hook(LifecyclePhase.STOPPING, func, priority=priority)
            return func
        return decorator