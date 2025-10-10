"""
Core application package.

Provides the main application orchestrator, menu system, and lifecycle management.

Example:
    >>> from amp_llm.core import Application
    >>> app = Application()
    >>> await app.run()
"""

from .app import Application
from .menu import MenuSystem, MenuItem, MenuAction
from .context import ApplicationContext
from .lifecycle import LifecycleManager, LifecycleHook
from .ssh_manager import SSHManager, SSHConnectionError
from .exceptions import (
    CoreError,
    ApplicationError,
    MenuError,
    GracefulExit,
)

# Backward compatibility alias for old code
AMPLLMApp = Application

__all__ = [
    # Main application
    'Application',
    'AMPLLMApp',  # Backward compatibility
    
    # Menu system
    'MenuSystem',
    'MenuItem',
    'MenuAction',
    
    # Context and lifecycle
    'ApplicationContext',
    'LifecycleManager',
    'LifecycleHook',
    
    # SSH management
    'SSHManager',
    'SSHConnectionError',
    
    # Exceptions
    'CoreError',
    'ApplicationError',
    'MenuError',
    'GracefulExit',
]

__version__ = '3.0.0'