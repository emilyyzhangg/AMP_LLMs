"""
Application context and state management.

Provides centralized state management for the application.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime
import asyncio

from src.amp_llm.config import AppConfig, get_config


@dataclass
class ApplicationContext:
    """
    Application context holding runtime state.
    
    This provides a centralized place to store application state
    that needs to be shared across components.
    
    Attributes:
        settings: Application settings
        ssh_manager: SSH connection manager
        running: Whether application is running
        start_time: Application start timestamp
        metadata: Additional runtime metadata
    """
    
    settings: AppConfig = field(default_factory=get_config)
    ssh_manager: Optional[Any] = None  # Type: SSHManager (avoid circular import)
    running: bool = True
    start_time: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Internal state
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    
    async def set_metadata(self, key: str, value: Any) -> None:
        """
        Set metadata value (thread-safe).
        
        Args:
            key: Metadata key
            value: Metadata value
        """
        async with self._lock:
            self.metadata[key] = value
    
    async def get_metadata(self, key: str, default: Any = None) -> Any:
        """
        Get metadata value (thread-safe).
        
        Args:
            key: Metadata key
            default: Default value if key not found
        
        Returns:
            Metadata value or default
        """
        async with self._lock:
            return self.metadata.get(key, default)
    
    def is_ssh_connected(self) -> bool:
        """Check if SSH is connected."""
        if not self.ssh_manager:
            return False
        return self.ssh_manager.is_connected()
    
    def get_uptime(self) -> float:
        """
        Get application uptime in seconds.
        
        Returns:
            Uptime in seconds
        """
        return (datetime.now() - self.start_time).total_seconds()
    
    def __repr__(self) -> str:
        """String representation."""
        ssh_status = "connected" if self.is_ssh_connected() else "disconnected"
        uptime = int(self.get_uptime())
        return (
            f"ApplicationContext(running={self.running}, "
            f"ssh={ssh_status}, uptime={uptime}s)"
        )