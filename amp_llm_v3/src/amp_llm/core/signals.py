"""
Signal handling for graceful shutdown.

Handles system signals (SIGINT, SIGTERM) for clean application exit.
"""

import signal
import asyncio
from typing import Callable, Optional, List
from functools import partial

from src.amp_llm.config import get_logger
from .exceptions import GracefulExit

logger = get_logger(__name__)


class SignalHandler:
    """
    Manages system signal handling for graceful shutdown.
    
    Example:
        >>> handler = SignalHandler()
        >>> handler.setup()
        >>> await handler.wait_for_signal()
    """
    
    def __init__(self):
        self.shutdown_event = asyncio.Event()
        self.shutdown_callbacks: List[Callable] = []
        self._original_handlers = {}
    
    def setup(self) -> None:
        """
        Set up signal handlers for SIGINT and SIGTERM.
        
        Registers handlers that trigger graceful shutdown.
        """
        # Store original handlers
        self._original_handlers = {
            signal.SIGINT: signal.getsignal(signal.SIGINT),
            signal.SIGTERM: signal.getsignal(signal.SIGTERM),
        }
        
        # Register new handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.debug("Signal handlers registered for SIGINT and SIGTERM")
    
    def _signal_handler(self, signum: int, frame) -> None:
        """
        Handle received signal.
        
        Args:
            signum: Signal number
            frame: Current stack frame
        """
        signal_name = signal.Signals(signum).name
        logger.info(f"Received signal {signal_name} ({signum}), initiating shutdown...")
        
        # Set shutdown event
        self.shutdown_event.set()
        
        # Run callbacks
        for callback in self.shutdown_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in shutdown callback: {e}")
    
    def add_shutdown_callback(self, callback: Callable) -> None:
        """
        Add callback to run when shutdown signal received.
        
        Args:
            callback: Function to call on shutdown
        """
        self.shutdown_callbacks.append(callback)
    
    async def wait_for_signal(self) -> None:
        """
        Wait for shutdown signal.
        
        This coroutine blocks until a signal is received.
        """
        await self.shutdown_event.wait()
    
    def restore_handlers(self) -> None:
        """Restore original signal handlers."""
        for sig, handler in self._original_handlers.items():
            signal.signal(sig, handler)
        
        logger.debug("Original signal handlers restored")
    
    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        return self.shutdown_event.is_set()


# Global signal handler instance
_signal_handler: Optional[SignalHandler] = None


def get_signal_handler() -> SignalHandler:
    """
    Get global signal handler instance (singleton).
    
    Returns:
        SignalHandler instance
    """
    global _signal_handler
    if _signal_handler is None:
        _signal_handler = SignalHandler()
    return _signal_handler


def setup_signal_handlers() -> SignalHandler:
    """
    Set up signal handlers and return handler instance.
    
    Returns:
        Configured SignalHandler instance
    """
    handler = get_signal_handler()
    handler.setup()
    return handler