"""
Progress indicators and spinners.
"""

import asyncio
import sys
from typing import Optional
from contextlib import asynccontextmanager

from colorama import Fore, Style


class Spinner:
    """
    Animated spinner for long-running operations.
    
    Example:
        >>> async with Spinner("Processing..."):
        ...     await long_operation()
    """
    
    FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    
    def __init__(self, message: str = "Working...", color: str = "cyan"):
        self.message = message
        self.color = getattr(Fore, color.upper(), Fore.CYAN)
        self.task: Optional[asyncio.Task] = None
        self.running = False
    
    async def _spin(self):
        """Animation loop."""
        idx = 0
        while self.running:
            frame = self.FRAMES[idx % len(self.FRAMES)]
            sys.stdout.write(f"\r{self.color}{frame} {self.message}{Style.RESET_ALL}")
            sys.stdout.flush()
            idx += 1
            await asyncio.sleep(0.1)
    
    async def start(self):
        """Start spinner."""
        self.running = True
        self.task = asyncio.create_task(self._spin())
    
    async def stop(self, final_message: Optional[str] = None):
        """Stop spinner."""
        self.running = False
        if self.task:
            await self.task
        
        # Clear line
        sys.stdout.write('\r' + ' ' * (len(self.message) + 10) + '\r')
        
        if final_message:
            print(final_message)
    
    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            await self.stop(f"{Fore.GREEN}✓ Done{Style.RESET_ALL}")
        else:
            await self.stop(f"{Fore.RED}✗ Failed{Style.RESET_ALL}")


class ProgressBar:
    """
    Progress bar for operations with known total.
    
    Example:
        >>> progress = ProgressBar(total=100, description="Downloading")
        >>> for i in range(100):
        ...     await asyncio.sleep(0.01)
        ...     progress.update(i + 1)
        >>> progress.close()
    """
    
    def __init__(
        self,
        total: int,
        description: str = "",
        width: int = 40,
        fill_char: str = "█",
        empty_char: str = "░",
    ):
        self.total = total
        self.description = description
        self.width = width
        self.fill_char = fill_char
        self.empty_char = empty_char
        self.current = 0
    
    def update(self, current: int):
        """Update progress."""
        self.current = min(current, self.total)
        self._render()
    
    def increment(self, amount: int = 1):
        """Increment progress."""
        self.update(self.current + amount)
    
    def _render(self):
        """Render progress bar."""
        percent = (self.current / self.total) * 100
        filled = int(self.width * self.current / self.total)
        bar = self.fill_char * filled + self.empty_char * (self.width - filled)
        
        sys.stdout.write(
            f"\r{Fore.CYAN}{self.description} "
            f"[{bar}] {percent:.1f}% ({self.current}/{self.total}){Style.RESET_ALL}"
        )
        sys.stdout.flush()
    
    def close(self):
        """Finish progress bar."""
        self.update(self.total)
        print()  # New line


class IndeterminateProgress:
    """
    Indeterminate progress indicator.
    
    For operations where total is unknown.
    
    Example:
        >>> progress = IndeterminateProgress("Searching...")
        >>> await progress.start()
        >>> await long_search()
        >>> await progress.stop()
    """
    
    def __init__(self, message: str = "Working..."):
        self.message = message
        self.dots = 0
        self.task: Optional[asyncio.Task] = None
        self.running = False
    
    async def _animate(self):
        """Animation loop."""
        while self.running:
            dots = "." * (self.dots % 4)
            sys.stdout.write(f"\r{Fore.CYAN}{self.message}{dots}   {Style.RESET_ALL}")
            sys.stdout.flush()
            self.dots += 1
            await asyncio.sleep(0.5)
    
    async def start(self):
        """Start animation."""
        self.running = True
        self.task = asyncio.create_task(self._animate())
    
    async def stop(self):
        """Stop animation."""
        self.running = False
        if self.task:
            await self.task
        
        # Clear line
        sys.stdout.write('\r' + ' ' * (len(self.message) + 10) + '\r')
        sys.stdout.flush()
    
    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()


@asynccontextmanager
async def progress_spinner(message: str):
    """
    Context manager for simple spinner.
    
    Example:
        >>> async with progress_spinner("Loading..."):
        ...     await load_data()
    """
    spinner = Spinner(message)
    await spinner.start()
    try:
        yield spinner
    finally:
        await spinner.stop()