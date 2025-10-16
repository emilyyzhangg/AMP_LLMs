"""
Persistent session manager for Ollama API connections.
Supports smart connection strategy: auto, direct, or tunnel.
"""
import asyncio
import aiohttp
from typing import Optional, List
from amp_llm.config import get_logger, get_config
from amp_llm.llm.utils.tunnel_manager import OllamaTunnelManager

logger = get_logger(__name__)


class OllamaSessionManager:
    """
    Persistent session with smart connection strategy.
    
    Connection strategies:
    - 'auto': Smart detection (tunnel for remote, direct for local)
    - 'direct': Always try direct connection
    - 'tunnel': Always use SSH tunnel
    """

    def __init__(self, host: str, port: int = 11434, ssh_connection=None):
        self.original_host = host
        self.current_host = host
        self.port = port
        self.ssh_connection = ssh_connection

        self.session: Optional[aiohttp.ClientSession] = None
        self.connector: Optional[aiohttp.TCPConnector] = None

        self.tunnel_manager = None
        self._using_tunnel = False
        self._remote_shell = None
        
        # Load connection strategy from config
        try:
            config = get_config()
            self.connection_strategy = config.llm.connection_strategy
        except Exception:
            self.connection_strategy = 'auto'
            logger.debug("Could not load connection strategy from config, using 'auto'")

    # --------------------------------------------------------------
    async def __aenter__(self):
        await self.start_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_session()

    # --------------------------------------------------------------
    @property
    def base_url(self) -> str:
        return f"http://{self.current_host}:{self.port}"

    async def _create_session(self):
        """Create persistent aiohttp session with keepalive."""
        if self.session and not self.session.closed:
            return

        self.connector = aiohttp.TCPConnector(
            ttl_dns_cache=300,
            limit=100,
            force_close=False,
            enable_cleanup_closed=True,
            keepalive_timeout=300
        )

        self.session = aiohttp.ClientSession(connector=self.connector)
        logger.info(f"Started persistent Ollama session: {self.base_url}")

    # --------------------------------------------------------------
    async def _detect_remote_shell(self):
        """Detect whether remote shell is zsh or bash."""
        if not self.ssh_connection:
            return "bash"

        try:
            result = await self.ssh_connection.run(
                "echo $SHELL",
                check=False,
                term_type=None
            )
            shell_path = (result.stdout or "").strip()
            if "zsh" in shell_path:
                logger.info(f"Detected remote shell: {shell_path}")
                self._remote_shell = "zsh"
            else:
                logger.info(f"Detected remote shell: {shell_path or 'bash (default)'}")
                self._remote_shell = "bash"
        except Exception as e:
            logger.warning(f"Could not detect remote shell: {e}")
            self._remote_shell = "bash"

        return self._remote_shell

    # --------------------------------------------------------------
    async def _run_silent(self, command: str):
        """
        Run a remote command without echoing user input.
        Works even when no TTY is allocated (term_type=None).
        """
        if not self.ssh_connection:
            raise RuntimeError("SSH connection not available for remote execution")

        # Force bash for consistent stty behavior on macOS (even if zsh default)
        wrapped = f'bash -lc "stty -echo; {command}; stty echo"'

        result = await self.ssh_connection.run(
            wrapped,
            check=False,
            term_type=None,
        )
        return result

    # --------------------------------------------------------------
    async def _test_connection(self) -> bool:
        """Check if Ollama API is alive."""
        try:
            async with self.session.get(
                f"{self.base_url}/api/tags",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.debug(f"Connection test failed: {e}")
            return False

    async def _create_tunnel(self) -> bool:
        """Create SSH tunnel when direct connection fails."""
        if not self.ssh_connection:
            logger.warning("SSH connection not available for tunneling")
            return False

        self.tunnel_manager = OllamaTunnelManager(
            self.ssh_connection,
            local_port=self.port,
            remote_port=self.port
        )

        if await self.tunnel_manager.create():
            self.current_host = "localhost"
            self._using_tunnel = True
            logger.info("✅ SSH tunnel established for Ollama")
            return True
        return False

    # --------------------------------------------------------------
    def _should_use_tunnel_immediately(self) -> bool:
        """Determine if we should skip direct connection and use tunnel."""
        # If no SSH, can't use tunnel
        if not self.ssh_connection:
            return False
        
        # If explicitly set to tunnel mode
        if self.connection_strategy == 'tunnel':
            return True
        
        # If auto mode and host is remote (not localhost)
        if self.connection_strategy == 'auto':
            is_remote = self.original_host not in ('localhost', '127.0.0.1', '::1')
            return is_remote
        
        return False

    # --------------------------------------------------------------
    async def _connect_via_tunnel(self):
        """Connect using SSH tunnel."""
        logger.info(f"Connecting via SSH tunnel to {self.original_host}:{self.port}")
        
        if await self._create_tunnel():
            await self.session.close()
            await self._create_session()
            
            if await self._test_connection():
                logger.info("✅ Connected via SSH tunnel")
                return self
            raise ConnectionError("Cannot connect via SSH tunnel")
        
        raise ConnectionError("Failed to create SSH tunnel")

    async def _connect_direct(self):
        """Connect directly without tunnel."""
        logger.info(f"Attempting direct connection to {self.original_host}:{self.port}")
        
        if await self._test_connection():
            logger.info("✅ Direct connection successful")
            return self
        
        raise ConnectionError(f"Cannot connect directly to {self.original_host}:{self.port}")

    async def _connect_auto(self):
        """Smart auto connection strategy."""
        # Check if we should skip direct and go straight to tunnel
        if self._should_use_tunnel_immediately():
            logger.info(
                f"Remote host detected ({self.original_host}), "
                "using SSH tunnel (skipping direct connection)"
            )
            return await self._connect_via_tunnel()
        
        # Try direct connection first
        logger.info("Attempting direct connection...")
        if await self._test_connection():
            logger.info("✅ Direct connection successful")
            return self
        
        # Fallback to tunnel if we have SSH
        if self.ssh_connection:
            logger.warning("⚠️  Direct connection failed, trying SSH tunnel")
            return await self._connect_via_tunnel()
        
        raise ConnectionError("Failed to connect to Ollama")

    # --------------------------------------------------------------
    async def start_session(self):
        """Initialize persistent session based on connection strategy."""
        await self._create_session()
        
        try:
            if self.connection_strategy == 'tunnel':
                return await self._connect_via_tunnel()
            elif self.connection_strategy == 'direct':
                return await self._connect_direct()
            else:  # 'auto'
                return await self._connect_auto()
        except ConnectionError as e:
            logger.error(f"Connection failed: {e}")
            raise

    async def close_session(self):
        """Close session and SSH tunnel."""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("Closed persistent Ollama session")

        if self.tunnel_manager:
            self.tunnel_manager.close()
            self.tunnel_manager = None
            logger.info("Closed SSH tunnel")

    async def is_alive(self) -> bool:
        """Check if session is alive."""
        if not self.session or self.session.closed:
            return False
        return await self._test_connection()

    async def list_models(self) -> List[str]:
        """List available Ollama models."""
        if not self.session or self.session.closed:
            await self.start_session()

        try:
            async with self.session.get(
                f"{self.base_url}/api/tags",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return [m["name"] for m in data.get("models", [])]
                else:
                    logger.error(f"API returned {resp.status}")
                    return []
        except Exception as e:
            logger.error(f"Error listing models: {e}", exc_info=True)
            return []

    async def send_prompt(self, model: str, prompt: str, temperature=0.7, max_retries=3) -> str:
        """Send prompt to Ollama with retries."""
        if not self.session or self.session.closed:
            await self.start_session()

        url = f"{self.base_url}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature}
        }

        for attempt in range(max_retries):
            try:
                async with self.session.post(
                    url, json=payload, timeout=aiohttp.ClientTimeout(total=600)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("response", "")
                    else:
                        text = await resp.text()
                        logger.error(f"API error {resp.status}: {text}")
                        return f"Error: API returned {resp.status}"
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
                await asyncio.sleep(2)

        return f"Error: Could not reach Ollama after {max_retries} attempts"