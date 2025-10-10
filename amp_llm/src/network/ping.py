# ============================================================================
# src/amp_llm/network/ping.py
# ============================================================================
"""
Network ping utility for host availability checking.
"""
import asyncio
import platform
from amp_llm.config.logging import get_logger

logger = get_logger(__name__)


async def ping_host(host: str, timeout: float = 1.0) -> bool:
    """
    Ping host to check availability.
    
    Args:
        host: Hostname or IP address
        timeout: Timeout in seconds
        
    Returns:
        True if host responds, False otherwise
    """
    plat = platform.system().lower()
    
    if plat.startswith('win'):
        cmd = f'ping -n 1 -w {int(timeout*1000)} {host}'
    else:
        cmd = f'ping -c 1 -W {int(timeout)} {host}'
    
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        
        await asyncio.wait_for(proc.communicate(), timeout=timeout+1)
        
        success = proc.returncode == 0
        
        if success:
            logger.debug(f"Ping successful: {host}")
        else:
            logger.debug(f"Ping failed: {host}")
        
        return success
        
    except asyncio.TimeoutError:
        logger.debug(f"Ping timeout: {host}")
        return False
    except Exception as e:
        logger.error(f"Ping error for {host}: {e}")
        return False
