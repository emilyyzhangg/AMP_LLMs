# ============================================================================
# src/amp_llm/network/ssh.py
# ============================================================================
"""
SSH connection management with keepalive support.
"""
import asyncssh
import asyncio
from typing import Optional
from colorama import Fore
from amp_llm.config.settings import get_config, get_logger

logger = get_logger(__name__)
config = get_config()


async def connect_ssh(
    ip: str,
    username: str,
    password: str,
    keepalive_interval: int = 15,
    keepalive_count_max: int = 3,
    connect_timeout: int = 30
) -> Optional[asyncssh.SSHClientConnection]:
    """
    Establish SSH connection with keepalive.
    
    Args:
        ip: Remote host IP/hostname
        username: SSH username
        password: SSH password
        keepalive_interval: Seconds between keepalive packets
        keepalive_count_max: Max failed keepalive attempts
        connect_timeout: Connection timeout in seconds
        
    Returns:
        SSH connection object or None if failed
    """
    try:
        logger.info(f"Connecting to {username}@{ip}")
        
        conn = await asyncssh.connect(
            host=ip,
            username=username,
            password=password,
            keepalive_interval=keepalive_interval,
            keepalive_count_max=keepalive_count_max,
            known_hosts=None,
            tcp_keepalive=True,
            client_keys=None,
            connect_timeout=connect_timeout,
        )
        
        logger.info(f"Successfully connected to {username}@{ip}")
        return conn
        
    except asyncssh.PermissionDenied:
        print(Fore.RED + "❌ Authentication failed.")
        logger.error("SSH authentication failed")
        return None
    except asyncio.TimeoutError:
        print(Fore.RED + f"❌ Connection timeout to {ip}")
        logger.error(f"SSH connection timeout to {ip}")
        return None
    except Exception as e:
        print(Fore.RED + f"❌ SSH connection error: {e}")
        logger.error(f"SSH connection error: {e}", exc_info=True)
        return None
