"""
SSH Tunnel Manager for Ollama API access.
Handles automatic tunnel creation when direct connection fails.
"""
import asyncio
from typing import Optional
from amp_llm.config.logging import get_logger

logger = get_logger(__name__)


class OllamaTunnelManager:
    """
    Manages SSH tunnel for Ollama API access.
    """

    def __init__(self, ssh_connection, local_port: int = 11434, remote_port: int = 11434):
        self.ssh = ssh_connection
        self.local_port = local_port
        self.remote_port = remote_port
        self.listener = None
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active and self.listener is not None

    async def create(self) -> bool:
        """Create SSH tunnel."""
        if self._active:
            logger.warning("Tunnel already active")
            return True

        try:
            logger.info(f"Creating SSH tunnel: localhost:{self.local_port} -> remote:{self.remote_port}")
            self.listener = await self.ssh.forward_local_port(
                '',  # all interfaces
                self.local_port,
                'localhost',
                self.remote_port
            )
            await asyncio.sleep(1)
            self._active = True
            logger.info("SSH tunnel established successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to create SSH tunnel: {e}", exc_info=True)
            self._active = False
            return False

    async def test(self) -> bool:
        """Test tunnel health."""
        if not self._active:
            return False

        try:
            import aiohttp
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(f"http://localhost:{self.local_port}/api/tags") as resp:
                    return resp.status == 200
        except Exception as e:
            logger.warning(f"Tunnel test failed: {e}")
            return False

    def close(self):
        """Close tunnel."""
        if self.listener:
            try:
                self.listener.close()
                logger.info("SSH tunnel closed")
            except Exception as e:
                logger.error(f"Error closing tunnel: {e}")
            finally:
                self.listener = None
                self._active = False


async def create_ollama_tunnel(ssh_connection, local_port=11434, remote_port=11434):
    manager = OllamaTunnelManager(ssh_connection, local_port, remote_port)
    if await manager.create():
        return manager
    return None
