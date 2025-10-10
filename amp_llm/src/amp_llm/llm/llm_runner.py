"""
LLM workflow runner with async input handling and file loading support.
Fixed: Better file search logic and clearer paste mode instructions.
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
    ssh_connection=ssh
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
        await aprint(Fore.CYAN + "💡 Commands:")
        await aprint(Fore.CYAN + "   • 'paste' - Enter multi-line paste mode (end with '<<<end' on new line)")
        await aprint(Fore.CYAN + "   • 'load <filename>' - Load file content")
        await aprint(Fore.CYAN + "   • 'load <filename> <question>' - Load file and ask question")
        await aprint(Fore.CYAN + "   • 'pwd' - Show current working directory")
        await aprint(Fore.CYAN + "   • 'ls' or 'dir' - List files in output/ directory\n")
        
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
                
                # Show current directory
                if prompt.lower() in ('pwd', 'cwd'):
                    await aprint(Fore.CYAN + f"📂 Current directory: {Path.cwd().absolute()}")
                    continue
                
                # List files in output directory
                if prompt.lower() in ('ls', 'dir', 'list'):
                    output_dir = Path('output')
                    await aprint(Fore.CYAN + f"📂 Current directory: {Path.cwd().absolute()}")
                    
                    if output_dir.exists() and output_dir.is_dir():
                        await aprint(Fore.CYAN + f"\n📁 Files in output/ directory:")
                        try:
                            files = list(output_dir.iterdir())
                            if files:
                                for f in sorted(files):
                                    size = f.stat().st_size if f.is_file() else 0
                                    ftype = "📄" if f.is_file() else "📁"
                                    await aprint(Fore.WHITE + f"  {ftype} {f.name} ({size:,} bytes)")
                            else:
                                await aprint(Fore.YELLOW + "  (empty directory)")
                        except Exception as e:
                            await aprint(Fore.RED + f"  Error: {e}")
                    else:
                        await aprint(Fore.YELLOW + "\n⚠️ output/ directory does not exist")
                        await aprint(Fore.CYAN + "Tip: Create it with files to load")
                    continue
                
                # Multi-line paste mode with improved instructions
                if prompt.lower() == 'paste':
                    await aprint(Fore.YELLOW + "\n📋 Multi-line paste mode activated")
                    await aprint(Fore.YELLOW + "Instructions:")
                    await aprint(Fore.YELLOW + "  1. Paste your content (JSON, text, code, etc.)")
                    await aprint(Fore.YELLOW + "  2. Press Enter after pasting")
                    await aprint(Fore.YELLOW + "  3. Type '<<<end' on a new line and press Enter")
                    await aprint(Fore.WHITE + "")
                    
                    lines = []
                    while True:
                        try:
                            line = await ainput('')
                            # Check for end marker (case insensitive)
                            if line.strip().lower() == '<<<end':
                                break
                            lines.append(line)
                        except KeyboardInterrupt:
                            await aprint(Fore.RED + "\n❌ Paste mode cancelled")
                            lines = []
                            break
                    
                    if not lines:
                        await aprint(Fore.RED + "No content captured.")
                        continue
                        
                    prompt = '\n'.join(lines)
                    
                    if not prompt.strip():
                        await aprint(Fore.RED + "No content provided.")
                        continue
                    
                    await aprint(Fore.GREEN + f"✅ Captured {len(lines)} lines ({len(prompt)} characters)")
                
                # Load file mode with improved path searching
                elif prompt.lower().startswith('load '):
                    # Extract filename and optional question
                    parts = prompt[5:].strip().split(maxsplit=1)
                    filename = parts[0]
                    initial_question = parts[1] if len(parts) > 1 else None
                    
                    # Normalize path separators for Windows
                    filename = filename.replace('\\', '/')
                    
                    # Search for file in multiple locations
                    search_paths = [
                        Path(filename),  # Exact path as given
                        Path('output') / filename,  # output directory
                        Path('output') / f"{filename}.txt",  # output with .txt
                        Path('output') / f"{filename}.json",  # output with .json
                        Path('.') / filename,  # current directory
                        Path('.') / f"{filename}.txt",  # current with .txt
                        Path('.') / f"{filename}.json",  # current with .json
                        Path('..') / filename,  # parent directory
                        Path('..') / 'output' / filename,  # parent's output dir
                    ]
                    
                    # Try to find the file
                    found_path = None
                    await aprint(Fore.YELLOW + f"🔍 Searching for: {filename}")
                    
                    for path in search_paths:
                        try:
                            if path.exists() and path.is_file():
                                found_path = path
                                await aprint(Fore.GREEN + f"✓ Found at: {path.absolute()}")
                                break
                            else:
                                logger.debug(f"Not found: {path.absolute()}")
                        except Exception as e:
                            logger.debug(f"Error checking {path}: {e}")
                            continue
                    
                    if not found_path:
                        await aprint(Fore.RED + f"❌ File not found: {filename}")
                        await aprint(Fore.YELLOW + f"\n📂 Current working directory: {Path.cwd().absolute()}")
                        await aprint(Fore.YELLOW + "\n🔍 Searched in:")
                        for path in search_paths:
                            try:
                                exists = "✓ EXISTS" if path.exists() else "✗ not found"
                                await aprint(Fore.YELLOW + f"  • {path.absolute()} [{exists}]")
                            except:
                                await aprint(Fore.YELLOW + f"  • {path} [invalid path]")
                        
                        # List files in output directory if it exists
                        output_dir = Path('output')
                        if output_dir.exists() and output_dir.is_dir():
                            await aprint(Fore.CYAN + f"\n📁 Files in output/ directory:")
                            try:
                                files = list(output_dir.iterdir())
                                if files:
                                    for f in sorted(files)[:10]:  # Show first 10 files
                                        await aprint(Fore.CYAN + f"  • {f.name}")
                                    if len(files) > 10:
                                        await aprint(Fore.CYAN + f"  ... and {len(files)-10} more")
                                else:
                                    await aprint(Fore.CYAN + "  (empty)")
                            except Exception as e:
                                await aprint(Fore.RED + f"  Error listing: {e}")
                        
                        await aprint(Fore.CYAN + "\n💡 Tips:")
                        await aprint(Fore.CYAN + "  • Check the exact filename (case-sensitive on some systems)")
                        await aprint(Fore.CYAN + "  • Try the full path: load C:\\Users\\...\\file.txt")
                        await aprint(Fore.CYAN + "  • Use forward slashes: load C:/Users/.../file.txt")
                        continue
                    
                    try:
                        # Read file with error handling for different encodings
                        try:
                            with open(found_path, 'r', encoding='utf-8') as f:
                                file_content = f.read()
                        except UnicodeDecodeError:
                            # Try with different encoding
                            with open(found_path, 'r', encoding='latin-1') as f:
                                file_content = f.read()
                        
                        await aprint(Fore.GREEN + f"✅ Loaded {found_path.name} from {found_path.parent}")
                        await aprint(Fore.GREEN + f"   Size: {len(file_content)} characters")
                        
                        # Show preview of content
                        preview = file_content[:200]
                        if len(file_content) > 200:
                            preview += "..."
                        await aprint(Fore.CYAN + f"   Preview: {preview}\n")
                        
                        # Ask for additional context if not provided in command
                        if initial_question:
                            context = initial_question
                            await aprint(Fore.CYAN + f"Question: {context}\n")
                        else:
                            context = await ainput(
                                Fore.CYAN + 
                                "Add a question/instruction (or press Enter to analyze file): "
                            )
                        
                        if context.strip():
                            prompt = f"{context.strip()}\n\n```\n{file_content}\n```"
                        else:
                            prompt = f"Please analyze this content:\n\n```\n{file_content}\n```"
                        
                    except Exception as e:
                        await aprint(Fore.RED + f"❌ Error loading file: {e}")
                        logger.error(f"Error loading file: {e}", exc_info=True)
                        continue
                
                if not prompt:
                    continue
                
                # Send prompt and stream response
                await aprint(Fore.YELLOW + f"\n🤔 Sending prompt ({len(prompt)} chars) and waiting for response...")
                try:
                    out = await send_and_stream(proc, prompt)
                    
                    if not out or len(out.strip()) < 10:
                        await aprint(Fore.RED + "⚠️ Model returned empty or very short response.")
                        await aprint(Fore.YELLOW + "This might indicate a problem with the model.")
                        await aprint(Fore.YELLOW + f"Raw output length: {len(out)}")
                        if out:
                            await aprint(Fore.CYAN + f"Raw output: {repr(out[:200])}")
                    else:
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