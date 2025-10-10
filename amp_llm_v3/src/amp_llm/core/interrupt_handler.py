"""
Global interrupt (Ctrl+C) handler for graceful exits.
Ensures all workflows can be interrupted and return to main menu.
"""
import asyncio
from functools import wraps
from colorama import Fore
from amp_llm.config import get_logger

logger = get_logger(__name__)

try:
    from aioconsole import aprint
except ImportError:
    async def aprint(*args, **kwargs):
        print(*args, **kwargs)


class InterruptSignal(Exception):
    """Custom exception for clean interrupt handling."""
    pass


def handle_interrupts(workflow_name: str = "workflow"):
    """
    Decorator to handle KeyboardInterrupt in async workflows.
    Ensures graceful return to main menu on Ctrl+C.
    
    Args:
        workflow_name: Name of workflow for logging
        
    Example:
        @handle_interrupts("NCT Lookup")
        async def run_nct_lookup():
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except KeyboardInterrupt:
                await aprint(
                    Fore.YELLOW + 
                    f"\n\n⚠️ {workflow_name} interrupted (Ctrl+C). Returning to main menu..."
                )
                logger.info(f"{workflow_name} interrupted by user (Ctrl+C)")
                return None
            except InterruptSignal:
                await aprint(
                    Fore.YELLOW + 
                    f"\n⚠️ {workflow_name} cancelled. Returning to main menu..."
                )
                logger.info(f"{workflow_name} cancelled by user")
                return None
        return wrapper
    return decorator


async def safe_ainput(prompt: str, allow_interrupt: bool = True) -> str:
    """
    Safe async input with interrupt handling.
    
    Args:
        prompt: Input prompt
        allow_interrupt: If True, Ctrl+C raises InterruptSignal
        
    Returns:
        User input string
        
    Raises:
        InterruptSignal: If Ctrl+C pressed and allow_interrupt=True
    """
    try:
        from aioconsole import ainput
    except ImportError:
        async def ainput(p):
            return input(p)
    
    try:
        return await ainput(prompt)
    except KeyboardInterrupt:
        if allow_interrupt:
            raise InterruptSignal()
        return ""
    except EOFError:
        if allow_interrupt:
            raise InterruptSignal()
        return ""


async def check_for_menu_exit(user_input: str) -> bool:
    """
    Check if user wants to return to main menu.
    
    Args:
        user_input: User input string
        
    Returns:
        True if should exit to menu, False otherwise
    """
    exit_commands = ['main menu', 'menu', 'exit', 'quit', 'back', '']
    return user_input.strip().lower() in exit_commands


async def run_with_interrupt_protection(coro, workflow_name: str = "Task"):
    """
    Run coroutine with interrupt protection.
    
    Args:
        coro: Coroutine to run
        workflow_name: Name for logging
        
    Returns:
        Result from coroutine, or None if interrupted
    """
    try:
        return await coro
    except KeyboardInterrupt:
        await aprint(
            Fore.YELLOW + 
            f"\n⚠️ {workflow_name} interrupted (Ctrl+C)"
        )
        logger.info(f"{workflow_name} interrupted")
        return None
    except asyncio.CancelledError:
        await aprint(
            Fore.YELLOW + 
            f"\n⚠️ {workflow_name} cancelled"
        )
        logger.info(f"{workflow_name} cancelled")
        return None
    except Exception as e:
        await aprint(Fore.RED + f"❌ {workflow_name} error: {e}")
        logger.error(f"{workflow_name} error: {e}", exc_info=True)
        return None


class InterruptContext:
    """
    Context manager for interrupt-safe code blocks.
    
    Example:
        async with InterruptContext("Data Processing") as ctx:
            # Your code here
            if ctx.interrupted:
                return
    """
    
    def __init__(self, name: str):
        self.name = name
        self.interrupted = False
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type == KeyboardInterrupt:
            self.interrupted = True
            await aprint(
                Fore.YELLOW + 
                f"\n⚠️ {self.name} interrupted (Ctrl+C)"
            )
            logger.info(f"{self.name} interrupted")
            return True  # Suppress the exception
        return False


# Convenience functions for common workflows

@handle_interrupts("Shell Session")
async def run_shell_safe(shell_func, *args, **kwargs):
    """Run shell session with interrupt handling."""
    return await shell_func(*args, **kwargs)


@handle_interrupts("LLM Session")
async def run_llm_safe(llm_func, *args, **kwargs):
    """Run LLM session with interrupt handling."""
    return await llm_func(*args, **kwargs)


@handle_interrupts("NCT Lookup")
async def run_nct_safe(nct_func, *args, **kwargs):
    """Run NCT lookup with interrupt handling."""
    return await nct_func(*args, **kwargs)


@handle_interrupts("Research Assistant")
async def run_research_safe(research_func, *args, **kwargs):
    """Run research assistant with interrupt handling."""
    return await research_func(*args, **kwargs)