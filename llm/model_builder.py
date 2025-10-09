"""
Model builder for Research Assistant.
Handles model creation with dynamic Modelfile generation.
"""
import asyncio
import time
import re
from pathlib import Path
from colorama import Fore
from config import get_logger

try:
    from aioconsole import ainput, aprint
except ImportError:
    async def ainput(prompt):
        return input(prompt)
    async def aprint(*args, **kwargs):
        print(*args, **kwargs)

logger = get_logger(__name__)


async def ensure_model_exists(ssh, model_name: str, models: list) -> bool:
    """
    Check if custom model exists, create if not.
    Uses dynamic Modelfile generation from validation_config.
    
    Args:
        ssh: SSH connection
        model_name: Name of custom model
        models: List of available models
        
    Returns:
        True if model ready, False otherwise
    """
    if model_name in models:
        await aprint(Fore.GREEN + f"✅ Using existing model: {model_name}")
        logger.info(f"Found existing model: {model_name}")
        return True
    
    await aprint(Fore.YELLOW + f"\n🔧 Custom model '{model_name}' not found")
    await aprint(Fore.CYAN + "This is a one-time setup to create a specialized model.")
    
    create = await ainput(Fore.GREEN + f"Create '{model_name}' now? (y/n) [y]: ")
        
    if create.strip().lower() in ('n', 'no'):
        await aprint(Fore.YELLOW + "Skipped. You can use a base model instead.")
        return False
    
    # Select base model
    await aprint(Fore.CYAN + f"\n📋 Available base models:")
    for i, model in enumerate(models, 1):
        await aprint(Fore.WHITE + f"  {i}) {model}")
    
    choice = await ainput(Fore.GREEN + f"Select base model [1]: ")
    
    base_model = None
    choice = choice.strip()
    
    if not choice:
        base_model = models[0] if models else 'llama3:8b'
    elif choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(models):
            base_model = models[idx]
        else:
            await aprint(Fore.RED + "Invalid selection, using first available model")
            base_model = models[0] if models else 'llama3:8b'
    else:
        if choice in models:
            base_model = choice
        else:
            await aprint(Fore.YELLOW + f"Model '{choice}' not found, using '{models[0] if models else 'llama3:8b'}'")
            base_model = models[0] if models else 'llama3:8b'
    
    await aprint(Fore.CYAN + f"\n🏗️  Building '{model_name}' from base model '{base_model}'...")
    
    # Generate Modelfile dynamically
    await aprint(Fore.CYAN + f"📝 Generating Modelfile from validation_config.py...")
    
    try:
        from generate_modelfile import generate_modelfile
        
        modelfile_content = generate_modelfile(base_model=base_model)
        
        await aprint(Fore.GREEN + f"✅ Generated Modelfile ({len(modelfile_content)} bytes)")
        
    except Exception as e:
        await aprint(Fore.RED + f"❌ Failed to generate Modelfile: {e}")
        logger.error(f"Modelfile generation error: {e}", exc_info=True)
        return False
    
    # Upload to remote server
    await aprint(Fore.CYAN + f"📤 Uploading Modelfile to remote server...")
    
    temp_modelfile = f"/tmp/ct_modelfile_{int(time.time())}.modelfile"
    
    try:
        async with ssh.start_sftp_client() as sftp:
            async with sftp.open(temp_modelfile, 'w') as remote_file:
                await remote_file.write(modelfile_content)
        
        await aprint(Fore.GREEN + f"✅ Uploaded to {temp_modelfile}")
    except Exception as e:
        await aprint(Fore.RED + f"❌ SFTP upload failed: {e}")
        logger.error(f"SFTP error: {e}", exc_info=True)
        return False
    
    # Build model
    await aprint(Fore.CYAN + f"🔨 Building model (this may take 1-2 minutes)...")
    
    try:
        result = await ssh.run(
            f'bash -l -c "ollama create {model_name} -f {temp_modelfile}"',
            check=False
        )
        
        # Cleanup temp file
        await ssh.run(f'rm -f {temp_modelfile}', check=False)
        
        if result.exit_status == 0:
            await aprint(Fore.GREEN + f"\n✅ Success! Model '{model_name}' created!")
            await aprint(Fore.CYAN + f"   Base: {base_model}")
            await aprint(Fore.CYAN + f"   Name: {model_name}")
            await aprint(Fore.CYAN + f"   Validation: Synced from validation_config.py ✓")
            logger.info(f"Created model {model_name} from {base_model}")
            return True
        else:
            await aprint(Fore.RED + f"\n❌ Model creation failed!")
            if result.stderr:
                await aprint(Fore.RED + f"Error: {result.stderr}")
            return False
            
    except Exception as e:
        await aprint(Fore.RED + f"❌ Error running ollama command: {e}")
        logger.error(f"Ollama create error: {e}", exc_info=True)
        await ssh.run(f'rm -f {temp_modelfile}', check=False)
        return False


async def rebuild_model(ssh, model_name: str, base_model: str) -> bool:
    """
    Rebuild existing model with updated validation config.
    
    Args:
        ssh: SSH connection
        model_name: Name of model to rebuild
        base_model: Base model to use
        
    Returns:
        True if successful
    """
    await aprint(Fore.YELLOW + f"\n🔄 Rebuilding '{model_name}' with latest validation config...")
    
    # Delete existing model
    try:
        result = await ssh.run(f'bash -l -c "ollama rm {model_name}"', check=False)
        if result.exit_status == 0:
            await aprint(Fore.GREEN + f"✅ Removed old model")
        else:
            await aprint(Fore.YELLOW + f"⚠️  Model may not exist: {result.stderr}")
    except Exception as e:
        await aprint(Fore.YELLOW + f"⚠️  Could not remove old model: {e}")
    
    # Create new model (will use latest validation config)
    return await ensure_model_exists(ssh, model_name, [base_model])


async def check_model_sync(ssh, model_name: str) -> bool:
    """
    Check if model is in sync with validation_config.py.
    
    Args:
        ssh: SSH connection
        model_name: Name of model to check
        
    Returns:
        True if in sync, False if needs rebuild
    """
    # This is a placeholder - in production, you might store
    # a version hash in the model's metadata to track sync
    
    await aprint(Fore.CYAN + f"\n🔍 Checking if '{model_name}' is in sync...")
    
    # For now, we'll just check if model exists
    # In the future, could store validation_config hash in model
    
    try:
        result = await ssh.run(f'bash -l -c "ollama show {model_name}"', check=False)
        
        if result.exit_status == 0:
            await aprint(Fore.GREEN + f"✅ Model exists")
            
            # TODO: Check version hash
            # if model_hash != current_config_hash:
            #     await aprint(Fore.YELLOW + "⚠️  Validation config has changed")
            #     return False
            
            return True
        else:
            await aprint(Fore.YELLOW + f"⚠️  Model not found")
            return False
            
    except Exception as e:
        logger.error(f"Error checking model: {e}")
        return False