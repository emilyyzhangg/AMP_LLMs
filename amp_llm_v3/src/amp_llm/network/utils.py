"""Shared utility functions for network operations."""

import asyncio
from typing import Tuple
from src.amp_llm.config import get_logger

logger = get_logger(__name__)


async def get_remote_user_host(ssh) -> Tuple[str, str]:
    """
    Get remote username and hostname.
    
    Args:
        ssh: Active SSH connection
        
    Returns:
        Tuple of (username, hostname)
    """
    try:
        user_result = await ssh.run("whoami", term_type=None, check=False)
        host_result = await ssh.run("hostname", term_type=None, check=False)
        
        user = (user_result.stdout or "").strip() or "user"
        host = (host_result.stdout or "").strip() or "remote"
        
        return user, host
    except Exception as e:
        logger.warning(f"Failed to get remote user/host: {e}")
        return "user", "remote"


async def detect_shell_type(ssh) -> str:
    """
    Detect remote shell type.
    
    Args:
        ssh: Active SSH connection
        
    Returns:
        Shell name (zsh, bash, fish, etc.)
    """
    try:
        result = await ssh.run("echo $SHELL", check=False, term_type=None)
        shell_path = (result.stdout or "").strip()
        
        if not shell_path:
            return "bash"
        
        # Extract shell name from path
        shell_name = shell_path.split('/')[-1]
        logger.info(f"Detected remote shell: {shell_name}")
        
        return shell_name
    except Exception as e:
        logger.error(f"Failed to detect shell: {e}")
        return "bash"