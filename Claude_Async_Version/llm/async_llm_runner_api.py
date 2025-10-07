"""
LLM workflow runner using Ollama HTTP API instead of SSH terminal.
This completely avoids the terminal fragmentation issue.
Automatically sets up SSH tunnel if direct connection fails.
"""
from colorama import Fore
from config import get_config, get_logger
import asyncio
from pathlib import Path

try:
    from aioconsole import ainput, aprint
except ImportError:
    async def ainput(prompt):
        return input(prompt)
    async def aprint(*args, **kwargs):
        print(*args, **kwargs)

logger = get_logger(__name__)
config = get_config()


async def run_llm_entrypoint_api(ssh):
    """Main LLM workflow using Ollama HTTP API with automatic SSH tunneling."""
    from llm.async_llm_utils import list_remote_models_api, send_to_ollama_api
    
    await aprint(Fore.CYAN + "=== ⚙️ LLM Workflow (API Mode) ===")
    logger.info("Starting LLM workflow in API mode")
    
    # Get SSH host info
    try:
        host = ssh._host if hasattr(ssh, '_host') else config.network.default_ip
    except:
        host = config.network.default_ip
    
    await aprint(Fore.YELLOW + f"Checking Ollama API at {host}:11434...")
    
    # Try direct connection first
    models = await list_remote_models_api(host)
    
    tunnel_listener = None  # Track tunnel for cleanup
    
    if not models:
        # Direct connection failed - try via SSH tunnel
        await aprint(Fore.YELLOW + "⚠️ Direct connection failed. Setting up SSH tunnel...")
        
        try:
            # Create SSH tunnel: local port 11434 -> remote localhost:11434
            tunnel_listener = await ssh.forward_local_port(
                '',  # Listen on all interfaces
                11434,  # Local port
                'localhost',  # Remote host (from server's perspective)
                11434  # Remote port
            )
            
            await aprint(Fore.GREEN + "✅ SSH tunnel created: localhost:11434 -> remote:11434")
            logger.info("SSH tunnel established")
            
            # Wait a moment for tunnel to be ready
            await asyncio.sleep(1)
            
            # Now try via localhost
            await aprint(Fore.YELLOW + "Connecting via SSH tunnel...")
            models = await list_remote_models_api('localhost')
            
            if not models:
                await aprint(Fore.RED + "⚠️ Still cannot connect to Ollama.")
                await aprint(Fore.YELLOW + "\nTroubleshooting:")
                await aprint(Fore.YELLOW + "  1. Check if Ollama is running on remote server:")
                await aprint(Fore.WHITE + "     SSH to server and run: ollama list")
                await aprint(Fore.YELLOW + "  2. Check Ollama service:")
                await aprint(Fore.WHITE + "     systemctl status ollama")
                await aprint(Fore.WHITE + "     ps aux | grep ollama")
                await aprint(Fore.YELLOW + "  3. Try starting Ollama:")
                await aprint(Fore.WHITE + "     ollama serve")
                logger.warning("No models found even via tunnel")
                
                # Cleanup tunnel
                if tunnel_listener:
                    tunnel_listener.close()
                
                return
            
            # Success via tunnel - use localhost for all API calls
            host = 'localhost'
            await aprint(Fore.GREEN + f"✅ Connected via tunnel! Using localhost:11434")
            
        except Exception as e:
            await aprint(Fore.RED + f"❌ Failed to create SSH tunnel: {e}")
            await aprint(Fore.YELLOW + "\nAlternative solutions:")
            await aprint(Fore.YELLOW + "  1. Open firewall on remote server: sudo ufw allow 11434/tcp")
            await aprint(Fore.YELLOW + "  2. Or use SSH terminal mode (option 3 from main menu)")
            logger.error(f"SSH tunnel failed: {e}")
            return
    else:
        await aprint(Fore.GREEN + f"✅ Direct connection successful!")
    
    # Display models
    await aprint(Fore.GREEN + f"\n✅ Found {len(models)} model(s):")
    for i, m in enumerate(models, 1):
        await aprint(f" {i}) {m}")
    
    # Prompt for model selection
    choice = await ainput(
        Fore.GREEN + "Select model by number or name: "
    )
    choice = choice.strip()
    
    if not choice:
        await aprint("Cancelled.")
        # Cleanup tunnel if created
        if tunnel_listener:
            tunnel_listener.close()
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
        # Cleanup tunnel if created
        if tunnel_listener:
            tunnel_listener.close()
        return
    
    await aprint(Fore.GREEN + f"\n✅ Using model: {model}")
    await aprint(Fore.CYAN + "\n💡 Commands:")
    await aprint(Fore.CYAN + "   • 'paste' - Enter multi-line paste mode")
    await aprint(Fore.CYAN + "   • 'load <filename>' - Load file content")
    await aprint(Fore.CYAN + "   • 'pwd' - Show current directory")
    await aprint(Fore.CYAN + "   • 'ls' - List files")
    await aprint(Fore.CYAN + "   • 'exit' or 'main menu' - Return\n")
    
    # Chat loop
    try:
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
                
                # List files
                if prompt.lower() in ('ls', 'dir', 'list'):
                    output_dir = Path('output')
                    await aprint(Fore.CYAN + f"📂 Current directory: {Path.cwd().absolute()}")
                    
                    if output_dir.exists() and output_dir.is_dir():
                        await aprint(Fore.CYAN + f"\n📁 Files in output/:")
                        try:
                            files = list(output_dir.iterdir())
                            if files:
                                for f in sorted(files):
                                    size = f.stat().st_size if f.is_file() else 0
                                    ftype = "📄" if f.is_file() else "📁"
                                    await aprint(Fore.WHITE + f"  {ftype} {f.name} ({size:,} bytes)")
                            else:
                                await aprint(Fore.YELLOW + "  (empty)")
                        except Exception as e:
                            await aprint(Fore.RED + f"  Error: {e}")
                    else:
                        await aprint(Fore.YELLOW + "\n⚠️ output/ directory does not exist")
                    continue
                
                # Paste mode
                if prompt.lower() == 'paste':
                    await aprint(Fore.YELLOW + "\n📋 Paste mode - End with '<<<end'")
                    lines = []
                    while True:
                        try:
                            line = await ainput('')
                            if line.strip().lower() == '<<<end':
                                break
                            lines.append(line)
                        except KeyboardInterrupt:
                            await aprint(Fore.RED + "\n❌ Cancelled")
                            lines = []
                            break
                    
                    if not lines:
                        continue
                        
                    prompt = '\n'.join(lines)
                    await aprint(Fore.GREEN + f"✅ Captured {len(lines)} lines ({len(prompt)} chars)")
                
                # Load file
                elif prompt.lower().startswith('load '):
                    parts = prompt[5:].strip().split(maxsplit=1)
                    filename = parts[0]
                    question = parts[1] if len(parts) > 1 else None
                    
                    # Search for file
                    search_paths = [
                        Path(filename),
                        Path('output') / filename,
                        Path('output') / f"{filename}.txt",
                        Path('output') / f"{filename}.json",
                    ]
                    
                    found = None
                    for path in search_paths:
                        if path.exists() and path.is_file():
                            found = path
                            break
                    
                    if not found:
                        await aprint(Fore.RED + f"❌ File not found: {filename}")
                        continue
                    
                    try:
                        with open(found, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        await aprint(Fore.GREEN + f"✅ Loaded {found.name} ({len(content)} chars)")
                        
                        if question:
                            prompt = f"{question}\n\n{content}"
                        else:
                            question = await ainput(Fore.CYAN + "Question (or Enter to analyze): ")
                            if question.strip():
                                prompt = f"{question}\n\n{content}"
                            else:
                                prompt = f"Please analyze this content:\n\n{content}"
                        
                    except Exception as e:
                        await aprint(Fore.RED + f"❌ Error: {e}")
                        continue
                
                if not prompt:
                    continue
                
                # Send to API
                await aprint(Fore.YELLOW + "\n🤔 Processing...")
                
                try:
                    response = await send_to_ollama_api(host, model, prompt)
                    
                    if response.startswith("Error:"):
                        await aprint(Fore.RED + f"\n{response}\n")
                    else:
                        await aprint(Fore.GREEN + '\n🧠 Response:')
                        await aprint(Fore.WHITE + response + '\n')
                        
                except Exception as e:
                    await aprint(Fore.RED + f"\n❌ Error: {e}\n")
                    logger.error(f"API error: {e}", exc_info=True)
                    
            except KeyboardInterrupt:
                await aprint(Fore.YELLOW + "\n\nInterrupted. Type 'exit' to quit.")
                continue
            except Exception as e:
                await aprint(Fore.RED + f"Unexpected error: {e}")
                logger.error(f"Error in chat loop: {e}", exc_info=True)
    
    finally:
        # Cleanup tunnel when exiting
        if tunnel_listener:
            try:
                tunnel_listener.close()
                await aprint(Fore.YELLOW + "Closed SSH tunnel.")
                logger.info("SSH tunnel closed")
            except Exception as e:
                logger.error(f"Error closing tunnel: {e}")