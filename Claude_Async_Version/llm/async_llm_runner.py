"""
LLM workflow runner with async input handling and file loading support.
"""
from colorama import Fore
from .async_llm_utils import list_remote_models, start_persistent_ollama, send_and_stream
from config import get_config, get_logger
import asyncio
from pathlib import Path

try:
    from aioconsole import ainput, aprint
except ImportError:
    # Fallback
    async def ainput(prompt):
        return input(prompt)
    async def aprint(*args, **kwargs):
        print(*args, **kwargs)

logger = get_logger(__name__)
config = get_config()


async def run_llm_entrypoint(ssh):
    """Main LLM workflow entry point."""
    await aprint(Fore.CYAN + "=== ⚙️ LLM Workflow ===")
    logger.info("Starting LLM workflow")
    
    # Check if connection is alive
    try:
        if ssh.is_closed():
            await aprint(Fore.RED + "SSH connection is closed.")
            await aprint(Fore.YELLOW + "Please restart the application to reconnect.")
            logger.warning("SSH connection closed when entering LLM workflow")
            return
    except AttributeError:
        # If is_closed() doesn't exist, try without check
        logger.warning("Cannot check SSH connection state, proceeding anyway")
    except Exception as e:
        await aprint(Fore.RED + f"Cannot verify SSH connection: {e}")
        logger.error(f"Error checking SSH connection: {e}")
        # Continue anyway - let the actual command fail if connection is bad
        pass
    
    # List available models
    models = await list_remote_models(ssh)
    if not models:
        await aprint(Fore.RED + "⚠️ No Ollama models found on remote.")
        await aprint(Fore.YELLOW + "Make sure Ollama is installed and has models.")
        await aprint(Fore.YELLOW + "Tip: SSH to the server and run 'ollama list' to verify.")
        logger.warning("No Ollama models found")
        return
    
    # Display models
    await aprint(Fore.CYAN + "\nAvailable models:")
    for i, m in enumerate(models, 1):
        await aprint(f" {i}) {m}")
    
    # Prompt for model selection
    choice = await ainput(
        Fore.GREEN + "Select model by number or name (blank to cancel): "
    )
    choice = choice.strip()
    
    if not choice:
        await aprint("Cancelled.")
        return
    
    # Parse choice
    model = None
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(models):
            model = models[idx]
    else:
        for m in models:
            if m.lower() == choice.lower():
                model = m
                break
    
    if not model:
        await aprint(Fore.RED + "Invalid model.")
        logger.warning(f"Invalid model choice: {choice}")
        return
    
    # Start model
    await aprint(Fore.YELLOW + f"Starting model: {model}")
    logger.info(f"Starting Ollama model: {model}")
    
    try:
        proc = await start_persistent_ollama(ssh, model)
    except Exception as e:
        await aprint(Fore.RED + f"Failed to start model: {e}")
        logger.error(f"Error starting model: {e}", exc_info=True)
        return
    
    # Chat loop
    try:
        await aprint(Fore.GREEN + "\n✅ Model ready! Type your prompts (or 'exit'/'main menu' to quit)")
        await aprint(Fore.CYAN + "💡 Commands: 'paste' for multi-line | 'load <filename>' to load file\n")
        
        while True:
            try:
                prompt = await ainput(Fore.CYAN + '>>> ' + Fore.WHITE)
                prompt = prompt.strip()
                
                if prompt.lower() in ('exit', 'quit'):
                    await aprint(Fore.YELLOW + "Exiting LLM workflow...")
                    break
                
                if prompt.lower() in ('main menu', 'menu'):
                    await aprint(Fore.YELLOW + "Returning to main menu...")
                    break
                
                # Multi-line paste mode
                if prompt.lower() == 'paste':
                    await aprint(Fore.YELLOW + "\n📋 Multi-line mode: Paste your content, then type '<<<END' on a new line")
                    lines = []
                    while True:
                        line = await ainput('')
                        if line.strip() == '<<<END':
                            break
                        lines.append(line)
                    prompt = '\n'.join(lines)
                    if not prompt.strip():
                        await aprint(Fore.RED + "No content provided.")
                        continue
                    await aprint(Fore.GREEN + f"✅ Captured {len(lines)} lines ({len(prompt)} characters)")
                
                # Load file mode
                elif prompt.lower().startswith('load '):
                    # Extract filename and optional question
                    parts = prompt[5:].strip().split(maxsplit=1)
                    filename = parts[0]
                    initial_question = parts[1] if len(parts) > 1 else None
                    
                    try:
                        filepath = Path(filename)
                        
                        # Try multiple locations
                        search_paths = [
                            filepath,  # Exact path as given
                            Path('output') / filename,  # output directory
                            Path('.') / filename,  # Current directory
                            Path(__file__).parent.parent / 'output' / filename,  # Relative to script
                        ]
                        
                        found_path = None
                        for path in search_paths:
                            if path.exists() and path.is_file():
                                found_path = path
                                break
                        
                        if not found_path:
                            await aprint(Fore.RED + f"❌ File not found: {filename}")
                            await aprint(Fore.YELLOW + f"Searched in:")
                            for p in search_paths[:3]:
                                await aprint(Fore.YELLOW + f"  - {p.absolute()}")
                            await aprint(Fore.CYAN + "\nTip: Use full path or put file in 'output' folder")
                            continue
                        
                        # Read file
                        with open(found_path, 'r', encoding='utf-8') as f:
                            file_content = f.read()
                        
                        await aprint(Fore.GREEN + f"✅ Loaded {found_path.name} from {found_path.parent} ({len(file_content)} characters)")
                        
                        # Ask for additional context if not provided in command
                        if initial_question:
                            context = initial_question
                        else:
                            context = await ainput(Fore.CYAN + "Add a question/instruction (or press Enter to just analyze): ")
                        
                        if context.strip():
                            prompt = f"{context.strip()}\n\n{file_content}"
                        else:
                            prompt = file_content
                        
                    except Exception as e:
                        await aprint(Fore.RED + f"❌ Error loading file: {e}")
                        logger.error(f"Error loading file: {e}", exc_info=True)
                        continue
                
                if not prompt:
                    continue
                
                # Send prompt and stream response
                await aprint(Fore.YELLOW + "\n🤔 Thinking...")
                try:
                    out = await send_and_stream(proc, prompt)
                    await aprint(Fore.GREEN + '\n🧠 Model output:')
                    await aprint(Fore.WHITE + out + '\n')
                except BrokenPipeError:
                    await aprint(Fore.RED + "\n❌ Connection to model lost. Please restart LLM workflow.")
                    logger.error("Model process died")
                    break
                except Exception as e:
                    await aprint(Fore.RED + f"\n❌ Error communicating with model: {e}")
                    logger.error(f"Error in model communication: {e}")
                    break
                
            except KeyboardInterrupt:
                await aprint(Fore.YELLOW + "\n\nInterrupted. Type 'exit' to quit or continue chatting.")
                continue
                
    finally:
        # Cleanup
        try:
            logger.info("Cleaning up Ollama process")
            if hasattr(proc.stdin, 'close'):
                proc.stdin.close()
            if hasattr(proc, 'terminate'):
                proc.terminate()
            if hasattr(proc, 'wait_closed'):
                await proc.wait_closed()
        except Exception as e:
            logger.error(f"Error cleaning up process: {e}")