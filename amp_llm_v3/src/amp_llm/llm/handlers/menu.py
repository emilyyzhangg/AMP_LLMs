"""
Interactive menu display for LLM mode.
"""
from colorama import Fore, Style

from amp_llm.cli.async_io import aprint


async def show_interactive_menu():
    """Display interactive menu options."""
    await aprint(Fore.CYAN + Style.BRIGHT + "\n" + "="*60)
    await aprint(Fore.CYAN + Style.BRIGHT + "  💬 INTERACTIVE LLM SESSION")
    await aprint(Fore.CYAN + Style.BRIGHT + "="*60 + Style.RESET_ALL)
    
    await aprint(Fore.YELLOW + "\n💡 Available Commands:")
    await aprint(Fore.WHITE + "  📋 File Operations:")
    await aprint(Fore.CYAN + "    • 'load <filename>' - Load file from output/")
    await aprint(Fore.CYAN + "    • 'paste' - Multi-line paste mode")
    await aprint(Fore.CYAN + "    • 'ls' or 'dir' - List files")
    
    await aprint(Fore.WHITE + "\n  ℹ️  Information:")
    await aprint(Fore.CYAN + "    • 'help' - Show this menu")
    await aprint(Fore.CYAN + "    • 'models' - List available models")
    
    await aprint(Fore.WHITE + "\n  🚪 Exit:")
    await aprint(Fore.CYAN + "    • 'exit', 'quit', 'main menu' - Return to main menu")
    await aprint(Fore.YELLOW + "    • Ctrl+C - Interrupt and return")
    
    await aprint(Fore.CYAN + "\n" + "="*60 + "\n")