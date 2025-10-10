"""
Network utilities package.

Provides SSH connection management, ping utilities, and interactive shell.
"""

from .ping import ping_host
from .ssh import connect_ssh
from .shell import open_interactive_shell

__all__ = [
    'ping_host',
    'connect_ssh',
    'open_interactive_shell',
]

__version__ = '3.0.0'