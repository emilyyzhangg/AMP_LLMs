# ============================================================================
# src/amp_llm/llm/models/builder.py
# ============================================================================
"""
Model builder for creating custom Ollama models.
"""
import time
from pathlib import Path
from colorama import Fore
from amp_llm.config.settings import get_logger

try:
    from aioconsole import ainput, aprint
except ImportError:
    async def ainput(prompt):
        return input(prompt)
    async def aprint(*args, **kwargs):
        print(*args, **kwargs)

logger = get_logger(__name__)


class ModelBuilder:
    """Builds custom Ollama models from Modelfiles."""
    
    def __init__(self, ssh_connection):
        """
        Initialize builder.
        
        Args:
            ssh_connection: Active SSH connection
        """
        self.ssh = ssh_connection
    
    async def model_exists(self, model_name: str) -> bool:
        """
        Check if model exists on remote.
        
        Args:
            model_name: Name of model
            
        Returns:
            True if model exists
        """
        try:
            result = await self.ssh.run(
                f'bash -l -c "ollama show {model_name}"',
                check=False
            )
            return result.exit_status == 0
        except Exception as e:
            logger.error(f"Error checking model: {e}")
            return False
    
    async def build_model(
        self,
        model_name: str,
        base_model: str,
        modelfile_content: str
    ) -> bool:
        """
        Build custom model from Modelfile.
        
        Args:
            model_name: Name for custom model
            base_model: Base model to use
            modelfile_content: Modelfile content
            
        Returns:
            True if successful
        """
        # Upload Modelfile
        temp_path = f"/tmp/modelfile_{int(time.time())}.modelfile"
        
        try:
            await aprint(Fore.CYAN + "📤 Uploading Modelfile...")
            
            async with self.ssh.start_sftp_client() as sftp:
                async with sftp.open(temp_path, 'w') as f:
                    await f.write(modelfile_content)
            
            await aprint(Fore.GREEN + f"✅ Uploaded to {temp_path}")
            
        except Exception as e:
            await aprint(Fore.RED + f"❌ Upload failed: {e}")
            logger.error(f"SFTP error: {e}")
            return False
        
        # Build model
        try:
            await aprint(Fore.CYAN + "🔨 Building model...")
            
            result = await self.ssh.run(
                f'bash -l -c "ollama create {model_name} -f {temp_path}"',
                check=False
            )
            
            # Cleanup
            await self.ssh.run(f'rm -f {temp_path}', check=False)
            
            if result.exit_status == 0:
                await aprint(Fore.GREEN + f"\n✅ Model '{model_name}' created!")
                logger.info(f"Built model: {model_name}")
                return True
            else:
                await aprint(Fore.RED + "❌ Build failed")
                if result.stderr:
                    await aprint(Fore.RED + f"Error: {result.stderr}")
                return False
        
        except Exception as e:
            await aprint(Fore.RED + f"❌ Build error: {e}")
            logger.error(f"Build error: {e}")
            await self.ssh.run(f'rm -f {temp_path}', check=False)
            return False