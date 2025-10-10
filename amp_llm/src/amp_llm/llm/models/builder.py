# src/amp_llm/llm/models/builder.py
"""
Model builder for creating custom Ollama models from Modelfiles.
"""
import time
from pathlib import Path
from colorama import Fore

try:
    from aioconsole import ainput, aprint
except ImportError:
    async def ainput(prompt):
        return input(prompt)
    async def aprint(*args, **kwargs):
        print(*args, **kwargs)

from amp_llm.config import get_logger

logger = get_logger(__name__)


async def build_custom_model(
    ssh_connection, 
    model_name: str, 
    available_models: list,
    selected_base_model: str = None  # NEW PARAMETER
) -> bool:
    """
    Build custom model from Modelfile.
    
    Args:
        ssh_connection: SSH connection
        model_name: Name for custom model
        available_models: List of available base models
        selected_base_model: Pre-selected base model (optional)
        
    Returns:
        True if successful
    """
    await aprint(Fore.CYAN + "\n🏗️  Building Custom Model")
    
    # Find Modelfile
    modelfile_path = _find_modelfile()
    
    if not modelfile_path:
        await aprint(Fore.RED + "❌ Modelfile not found!")
        await aprint(Fore.YELLOW + "Expected locations:")
        await aprint(Fore.WHITE + "  • Project root: Modelfile")
        await aprint(Fore.WHITE + "  • amp_llm directory: amp_llm/Modelfile")
        await aprint(Fore.CYAN + "\nCreate one with:")
        await aprint(Fore.WHITE + "  python scripts/generate_modelfile.py")
        return False
    
    await aprint(Fore.GREEN + f"✅ Found Modelfile: {modelfile_path}")
    
    # Read Modelfile
    try:
        modelfile_content = modelfile_path.read_text()
    except Exception as e:
        await aprint(Fore.RED + f"❌ Cannot read Modelfile: {e}")
        return False
    
    # Use pre-selected base model or prompt for selection
    if selected_base_model:
        base_model = selected_base_model
        await aprint(Fore.CYAN + f"Using selected base model: {base_model}")
    else:
        # Original selection logic (fallback)
        await aprint(Fore.CYAN + f"\n📋 Available base models:")
        for i, model in enumerate(available_models, 1):
            await aprint(Fore.WHITE + f"  {i}. {model}")
        
        choice = await ainput(Fore.GREEN + "Select base model [1]: ")
        choice = choice.strip()
        
        # Parse choice
        base_model = None
        if not choice:
            base_model = available_models[0]
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(available_models):
                base_model = available_models[idx]
            else:
                await aprint(Fore.YELLOW + "Invalid selection, using first model")
                base_model = available_models[0]
        elif choice in available_models:
            base_model = choice
        else:
            await aprint(Fore.YELLOW + f"Model '{choice}' not found, using first model")
            base_model = available_models[0]
    
    await aprint(Fore.CYAN + f"\n🔨 Building '{model_name}' from '{base_model}'...")
    
    # Update FROM line in Modelfile
    updated_modelfile = _update_modelfile_base(modelfile_content, base_model)
    
    # Upload Modelfile
    temp_path = f"/tmp/amp_modelfile_{int(time.time())}.modelfile"
    
    try:
        await aprint(Fore.CYAN + "📤 Uploading Modelfile...")
        
        async with ssh_connection.start_sftp_client() as sftp:
            async with sftp.open(temp_path, 'w') as f:
                await f.write(updated_modelfile)
        
        await aprint(Fore.GREEN + f"✅ Uploaded to {temp_path}")
        
    except Exception as e:
        await aprint(Fore.RED + f"❌ Upload failed: {e}")
        logger.error(f"SFTP error: {e}")
        return False
    
    # Build model
    try:
        await aprint(Fore.CYAN + "🏗️  Building model (this may take 1-2 minutes)...")
        await aprint(Fore.YELLOW + "   Please wait...")
        
        result = await ssh_connection.run(
            f'bash -l -c "ollama create {model_name} -f {temp_path}"',
            check=False
        )
        
        # Cleanup
        await ssh_connection.run(f'rm -f {temp_path}', check=False)
        
        if result.exit_status == 0:
            await aprint(Fore.GREEN + f"\n✅ Success! Model '{model_name}' created!")
            await aprint(Fore.CYAN + f"   Base: {base_model}")
            await aprint(Fore.CYAN + f"   Name: {model_name}")
            return True
        else:
            await aprint(Fore.RED + "\n❌ Model creation failed!")
            if result.stderr:
                await aprint(Fore.RED + f"Error: {result.stderr}")
            return False
            
    except Exception as e:
        await aprint(Fore.RED + f"❌ Build error: {e}")
        logger.error(f"Build error: {e}", exc_info=True)
        
        # Cleanup on error
        try:
            await ssh_connection.run(f'rm -f {temp_path}', check=False)
        except:
            pass
        
        return False


def _find_modelfile() -> Path:
    """
    Find Modelfile in expected locations.
    
    Returns:
        Path to Modelfile or None if not found
    """
    search_paths = [
        Path("Modelfile"),  # Project root
        Path("amp_llm/Modelfile"),  # amp_llm directory
        Path("../Modelfile"),  # Parent directory
        Path("src/Modelfile"),  # src directory
    ]
    
    for path in search_paths:
        if path.exists():
            return path
    
    return None


def _update_modelfile_base(modelfile_content: str, base_model: str) -> str:
    """
    Update FROM line in Modelfile.
    
    Args:
        modelfile_content: Original Modelfile content
        base_model: New base model name
        
    Returns:
        Updated Modelfile content
    """
    import re
    
    # Replace FROM line
    updated = re.sub(
        r'^FROM\s+\S+',
        f'FROM {base_model}',
        modelfile_content,
        flags=re.MULTILINE
    )
    
    return updated