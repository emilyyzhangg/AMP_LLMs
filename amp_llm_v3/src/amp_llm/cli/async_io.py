"""
Async I/O utilities - single source for ainput/aprint.
"""

try:
    from aioconsole import ainput, aprint
except ImportError:
    # Fallback for environments without aioconsole
    async def ainput(prompt: str = "") -> str:
        """Async input fallback."""
        return input(prompt)
    
    async def aprint(*args, **kwargs) -> None:
        """Async print fallback."""
        print(*args, **kwargs)

__all__ = ['ainput', 'aprint']