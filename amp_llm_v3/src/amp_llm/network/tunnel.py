from amp_llm.config import get_logger

logger = get_logger(__name__)


class SSHTunnel:
    """SSH tunnel manager with proper cleanup."""
    
    def __init__(self, ssh_connection):
        self.ssh = ssh_connection
        self.listener = None
        self.local_port = None
        self.remote_host = None
        self.remote_port = None
        self._closed = False
    
    async def create_tunnel(
        self,
        local_port: int,
        remote_host: str = 'localhost',
        remote_port: int = 11434
    ):
        """Create SSH tunnel with port forwarding."""
        try:
            logger.info(
                f"Creating tunnel: localhost:{local_port} -> "
                f"{remote_host}:{remote_port}"
            )
            
            self.listener = await self.ssh.forward_local_port(
                '',
                local_port,
                remote_host,
                remote_port
            )
            
            self.local_port = local_port
            self.remote_host = remote_host
            self.remote_port = remote_port
            
            logger.info(f"Tunnel established on port {local_port}")
            
        except Exception as e:
            logger.error(f"Failed to create tunnel: {e}")
            raise
    
    async def close(self):
        """Close the tunnel gracefully."""
        if self._closed:
            return
        
        self._closed = True
        
        if self.listener:
            try:
                # Close with timeout
                await asyncio.wait_for(self._close_listener(), timeout=3.0)
                logger.info("Tunnel closed")
            except asyncio.TimeoutError:
                logger.warning("Tunnel close timeout")
            except Exception as e:
                logger.error(f"Error closing tunnel: {e}")
    
    async def _close_listener(self):
        """Internal close method."""
        self.listener.close()
        await self.listener.wait_closed()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
