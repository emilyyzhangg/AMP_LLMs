# ============================================================================
# src/amp_llm/llm/clients/ollama_ssh.py
# ============================================================================
"""
Ollama SSH client using terminal interaction.
Legacy method - has fragmentation issues, prefer API client.
"""
import asyncio
import re
from typing import List, AsyncGenerator, TYPE_CHECKING
if TYPE_CHECKING:
    from amp_llm.core import SSHManager
from amp_llm.config.settings import get_config
from amp_llm.config.logging import get_logger
from .base import BaseLLMClient

logger = get_logger(__name__)
config = get_config()

# ANSI escape sequence pattern
ANSI_ESCAPE = re.compile(r'(?:\x1B[@-_][0-?]*[ -/]*[@-~])')


def clean_ansi(text: str) -> str:
    """Remove ANSI escape sequences."""
    return ANSI_ESCAPE.sub('', text).strip()


class OllamaSSHClient(BaseLLMClient):
    """Ollama client using SSH terminal (legacy)."""
    
    def __init__(self, ssh_connection: 'SSHManager'):  # String annotation
        """
        Initialize SSH client.
        
        Args:
            ssh_connection: Active AsyncSSH connection
        """
        self.ssh = ssh_connection
        self.process = None
    
    async def list_models(self) -> List[str]:
        """List models via SSH command."""
        try:
            if self.ssh.is_closed():
                logger.error("SSH connection is closed")
                return []
            
            # Try multiple commands to find ollama
            commands = [
                'ollama list',
                '~/.ollama/bin/ollama list',
                '/usr/local/bin/ollama list',
                'bash -l -c "ollama list"',
            ]
            
            for cmd in commands:
                try:
                    result = await self.ssh.run(cmd, check=False)
                    
                    if result.exit_status == 0:
                        output = result.stdout or result.stderr
                        
                        if output and 'NAME' in output:
                            models = []
                            for line in output.splitlines():
                                line = line.strip()
                                if not line or line.lower().startswith('name'):
                                    continue
                                
                                parts = line.split()
                                if parts:
                                    models.append(parts[0])
                            
                            if models:
                                logger.info(f"Found {len(models)} models via SSH")
                                return models
                                
                except Exception as e:
                    logger.debug(f"Command '{cmd}' failed: {e}")
                    continue
            
            logger.warning("No models found via SSH")
            return []
            
        except Exception as e:
            logger.error(f"Error listing models: {e}")
            return []
    
    async def start_model(self, model: str):
        """Start persistent ollama process."""
        logger.info(f"Starting model: {model}")
        
        try:
            command = f'bash -l -c "ollama run {model}"'
            
            self.process = await self.ssh.create_process(
                command,
                term_type='xterm',
                encoding=None
            )
            
            # Wait for model to initialize
            await asyncio.sleep(3)
            
            if self.process.exit_status is not None:
                raise Exception(f"Process exited: {self.process.exit_status}")
            
            logger.info(f"Model {model} started")
            
        except Exception as e:
            logger.error(f"Failed to start model: {e}")
            raise
    
    async def generate(self, model: str, prompt: str) -> str:
        """Generate response via SSH terminal."""
        if not self.process:
            await self.start_model(model)
        
        # Send prompt
        full_prompt = (prompt + "\n").encode('utf-8')
        self.process.stdin.write(full_prompt)
        await self.process.stdin.drain()
        
        # Wait briefly
        await asyncio.sleep(1.0)
        
        # Read response
        output = []
        idle_count = 0
        max_idle = config.llm.idle_timeout
        chunk_size = config.llm.stream_chunk_size
        
        while True:
            try:
                chunk = await asyncio.wait_for(
                    self.process.stdout.read(chunk_size),
                    timeout=1.0
                )
                
                if not chunk:
                    break
                
                text = chunk.decode('utf-8', errors='ignore')
                output.append(text)
                idle_count = 0
                
            except asyncio.TimeoutError:
                idle_count += 1
                if idle_count > max_idle:
                    break
                continue
            except Exception as e:
                logger.error(f"Read error: {e}")
                break
        
        response = ''.join(output)
        response = clean_ansi(response)
        
        logger.info(f"Generated {len(response)} characters")
        return response
    
    async def generate_stream(
        self,
        model: str,
        prompt: str
    ) -> AsyncGenerator[str, None]:
        """Stream response via SSH terminal."""
        if not self.process:
            await self.start_model(model)
        
        # Send prompt
        full_prompt = (prompt + "\n").encode('utf-8')
        self.process.stdin.write(full_prompt)
        await self.process.stdin.drain()
        
        await asyncio.sleep(1.0)
        
        # Stream response
        idle_count = 0
        max_idle = config.llm.idle_timeout
        
        while True:
            try:
                chunk = await asyncio.wait_for(
                    self.process.stdout.read(1024),
                    timeout=1.0
                )
                
                if not chunk:
                    break
                
                text = chunk.decode('utf-8', errors='ignore')
                text = clean_ansi(text)
                
                if text:
                    yield text
                
                idle_count = 0
                
            except asyncio.TimeoutError:
                idle_count += 1
                if idle_count > max_idle:
                    break
                continue
            except Exception as e:
                logger.error(f"Stream error: {e}")
                break
    
    async def cleanup(self):
        """Cleanup process."""
        if self.process:
            try:
                if hasattr(self.process.stdin, 'close'):
                    self.process.stdin.close()
                if hasattr(self.process, 'terminate'):
                    self.process.terminate()
                if hasattr(self.process, 'wait_closed'):
                    await self.process.wait_closed()
            except Exception as e:
                logger.error(f"Cleanup error: {e}")