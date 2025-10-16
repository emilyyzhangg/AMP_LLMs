"""
Interactive session handler with command processing.
"""
from colorama import Fore

from amp_llm.cli.async_io import ainput, aprint
from amp_llm.config import get_logger
from amp_llm.llm.utils.interactive import (
    handle_paste_command,
    handle_load_command,
    list_output_files,
    show_pwd,
)
from .menu import show_interactive_menu

logger = get_logger(__name__)


async def run_interactive_session(session, model: str, ssh_manager):
    """
    Run enhanced interactive session with all features.
    
    Args:
        session: OllamaSessionManager instance
        model: Selected model name
        ssh_manager: SSH manager (for any SSH operations)
    """
    while True:
        try:
            prompt = await ainput(Fore.GREEN + "LLM >>> " + Fore.WHITE)
            
            if prompt is None:
                prompt = ""
            prompt = prompt.strip()
            
            if not prompt:
                continue
            
            # Check for exit commands
            if prompt.lower() in ("exit", "quit", "main menu"):
                await aprint(Fore.YELLOW + "Returning to main menu...")
                break
            
            # Handle special commands
            if await handle_special_command(prompt, session, model):
                continue
            
            # Regular prompt to LLM
            await aprint(Fore.YELLOW + f"\n🤔 Generating response...")
            
            try:
                response = await session.send_prompt(
                    model=model,
                    prompt=prompt,
                    temperature=0.7,
                    max_retries=3
                )
                
                if response.startswith("Error:"):
                    await aprint(Fore.RED + f"\n{response}")
                else:
                    await aprint(Fore.GREEN + "\n🧠 Response:")
                    await aprint(Fore.WHITE + response + "\n")
                    
            except Exception as e:
                await aprint(Fore.RED + f"\n❌ Error: {e}")
                logger.error(f"Generation error: {e}", exc_info=True)
                
        except KeyboardInterrupt:
            await aprint(Fore.YELLOW + "\n\n⚠️ Interrupted. Type 'exit' to quit...")
            continue
        except EOFError:
            await aprint(Fore.YELLOW + "\nEOF detected. Returning to main menu...")
            break


async def handle_special_command(prompt: str, session, model: str) -> bool:
    """
    Handle special commands. Returns True if command was handled.
    
    Args:
        prompt: User input
        session: Ollama session
        model: Current model
        
    Returns:
        True if command processed, False otherwise
    """
    prompt_lower = prompt.lower()
    
    # Help command
    if prompt_lower in ('help', '?', '!help'):
        await show_interactive_menu()
        return True
    
    # Directory listing
    if prompt_lower in ('ls', 'dir', 'list'):
        await list_output_files(aprint)
        return True
    
    # Show working directory
    if prompt_lower in ('pwd', 'cwd'):
        await show_pwd(aprint)
        return True
    
    # Paste mode
    if prompt_lower == 'paste':
        pasted = await handle_paste_command(ainput, aprint)
        if pasted:
            await aprint(Fore.YELLOW + f"\n🤔 Sending to LLM...")
            response = await session.send_prompt(model=model, prompt=pasted)
            if not response.startswith("Error:"):
                await aprint(Fore.GREEN + "\n🧠 Response:")
                await aprint(Fore.WHITE + response + "\n")
            else:
                await aprint(Fore.RED + f"\n{response}")
        return True
    
    # Load file
    if prompt_lower.startswith('load '):
        final_prompt = await handle_load_command(prompt, ainput, aprint, logger)
        if final_prompt:
            await aprint(Fore.YELLOW + f"\n🤔 Processing file...")
            response = await session.send_prompt(model=model, prompt=final_prompt)
            if not response.startswith("Error:"):
                await aprint(Fore.GREEN + "\n🧠 Response:")
                await aprint(Fore.WHITE + response + "\n")
            else:
                await aprint(Fore.RED + f"\n{response}")
        return True
    
    # List models
    if prompt_lower in ('models', 'list models'):
        models = await session.list_models()
        await aprint(Fore.CYAN + f"\n📋 Available models ({len(models)}):")
        for i, m in enumerate(models, 1):
            await aprint(Fore.WHITE + f"  {i}. {m}")
        await aprint("")
        return True
    
    return False