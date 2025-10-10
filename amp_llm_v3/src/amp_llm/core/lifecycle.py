"""
Application lifecycle management.

Provides hooks for startup, shutdown, and cleanup operations.
"""

import asyncio
from typing import Callable, Awaitable, List, Optional
from enum import Enum
from dataclasses import dataclass

from src.amp_llm.config import get_logger

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
    """
    Represents a lifecycle hook.
    
    Attributes:
        name: Hook name
        phase: Lifecycle phase when hook runs
        callback: Async function to call
        priority: Execution priority (lower runs first)
    """
    name: str
    phase: LifecyclePhase
    callback: Callable[[], Awaitable[None]]
    priority: int = 0


class LifecycleManager:
    """
    Manages application lifecycle hooks.
    
    Allows registering callbacks for different lifecycle phases
    (startup, shutdown, etc.) with priority ordering.
    
    Example:
        >>> manager = LifecycleManager()
        >>> 
        >>> @manager.on_startup
        ... async def init_database():
        ...     print("Initializing database...")
        >>> 
        >>> await manager.run_startup_hooks()
    """
    
    def __init__(self):
        self.hooks: List[LifecycleHook] = []
        self.current_phase = LifecyclePhase.INITIALIZING
    
    def register_hook(
        self,
        phase: LifecyclePhase,
        callback: Callable[[], Awaitable[None]],
        name: Optional[str] = None,
        priority: int = 0,
    ) -> None:
        """
        Register a lifecycle hook.
        
        Args:
            phase: Lifecycle phase
            callback: Async callback function
            name: Hook name (defaults to callback name)
            priority: Execution priority (lower = earlier)
        """
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
        """
        Run all hooks for a specific phase.
        
        Args:
            phase: Lifecycle phase to run
        """
        # Get hooks for this phase
        phase_hooks = [h for h in self.hooks if h.phase == phase]
        
        # Sort by priority
        phase_hooks.sort(key=lambda h: h.priority)
        
        logger.info(f"Running {len(phase_hooks)} {phase.value} hook(s)")
        
        # Run hooks
        for hook in phase_hooks:
            try:
                logger.debug(f"Running {phase.value} hook: {hook.name}")
                await hook.callback()
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
        """Run shutdown hooks."""
        self.current_phase = LifecyclePhase.STOPPING
        await self.run_hooks(LifecyclePhase.STOPPING)
        self.current_phase = LifecyclePhase.STOPPED
    
    # Decorator shortcuts
    def on_startup(self, priority: int = 0):
        """
        Decorator to register startup hook.
        
        Example:
            >>> @manager.on_startup(priority=10)
            ... async def setup():
            ...     print("Setting up...")
        """
        def decorator(func: Callable[[], Awaitable[None]]):
            self.register_hook(LifecyclePhase.STARTING, func, priority=priority)
            return func
        return decorator
    
    def on_shutdown(self, priority: int = 0):
        """
        Decorator to register shutdown hook.
        
        Example:
            >>> @manager.on_shutdown
            ... async def cleanup():
            ...     print("Cleaning up...")
        """
        def decorator(func: Callable[[], Awaitable[None]]):
            self.register_hook(LifecyclePhase.STOPPING, func, priority=priority)
            return func
        return decorator