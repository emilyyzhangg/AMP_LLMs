"""
SSH connection management with keepalive support.
"""
import asyncssh
import asyncio
from colorama import Fore
from config import get_config

config = get_config()


async def connect_ssh(ip, username, password):
    """
    Attempt SSH connection with keepalive configuration.
    
    Args:
        ip: Remote host IP
        username: SSH username
        password: SSH password
        
    Returns:
        SSH connection object or None if failed
    """
    try:
        conn = await asyncssh.connect(
            host=ip,
            username=username,
            password=password,
            keepalive_interval=config.network.ssh_keepalive_interval,
            keepalive_count_max=config.network.ssh_keepalive_count_max,
            known_hosts=None  # Don't verify host keys (for convenience)
        )
        return conn
    except asyncssh.PermissionDenied:
        print(Fore.RED + "Authentication failed.")
        return None
    except Exception as e:
        print(Fore.RED + f"SSH connection error: {e}")
        return None