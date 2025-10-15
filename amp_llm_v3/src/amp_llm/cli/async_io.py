import asyncio
import sys
import os
from typing import Optional

# Fix stdin/stdout blocking mode on module import
def _ensure_blocking_io():
    """Ensure all standard streams are in blocking mode."""
    try:
        import fcntl
        for stream in [sys.stdin, sys.stdout, sys.stderr]:
            if hasattr(stream, 'fileno'):
                try:
                    fd = stream.fileno()
                    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
                    if flags & os.O_NONBLOCK:
                        # Remove non-blocking flag
                        fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)
                except (OSError, ValueError, AttributeError):
                    pass
    except (ImportError, Exception):
        pass  # Windows or unable to fix

# Apply fix immediately on import
_ensure_blocking_io()


async def ainput(prompt: str = "") -> str:
    """
    Async input with robust error handling.
    
    This function ensures stdin is in blocking mode and properly
    handles EOF, KeyboardInterrupt, and cancellation.
    
    Args:
        prompt: Prompt string to display
        
    Returns:
        User input string
        
    Raises:
        EOFError: If input stream is closed
        asyncio.CancelledError: If task is cancelled
        KeyboardInterrupt: If Ctrl+C is pressed
    """
    # Ensure stdin is blocking before every input
    _ensure_blocking_io()
    
    # Check if stdin is a TTY
    if not sys.stdin.isatty():
        raise EOFError("stdin is not a terminal")
    
    # Use run_in_executor to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    
    try:
        # Run input() in a thread executor
        result = await loop.run_in_executor(None, _safe_input, prompt)
        return result
    except EOFError:
        # Input stream closed - propagate
        raise
    except KeyboardInterrupt:
        # User pressed Ctrl+C - propagate
        raise
    except asyncio.CancelledError:
        # Task cancelled - propagate
        raise
    except Exception as e:
        # Unexpected error
        import logging
        logging.error(f"ainput error: {e}", exc_info=True)
        raise EOFError(f"Input error: {e}")


def _safe_input(prompt: str) -> str:
    """
    Safe input function to run in executor thread.
    
    This runs in a separate thread, so it can block without
    affecting the async event loop.
    
    Args:
        prompt: Prompt string
        
    Returns:
        User input
        
    Raises:
        EOFError: If input fails
        KeyboardInterrupt: If Ctrl+C pressed
    """
    # Double-check stdin is blocking (thread-safe)
    _ensure_blocking_io()
    
    try:
        # This will block in the thread, not the event loop
        return input(prompt)
    except EOFError:
        # End of input
        raise
    except KeyboardInterrupt:
        # Ctrl+C
        raise
    except Exception as e:
        # Any other error - convert to EOFError
        raise EOFError(f"Input failed: {e}")


async def aprint(*args, **kwargs):
    """
    Async print that handles non-blocking stdout.
    
    IMPORTANT: Cannot pass keyword arguments through run_in_executor.
    We extract and handle them separately.
    
    Args:
        *args: Arguments to print
        **kwargs: Keyword arguments for print (sep, end, file, flush)
    """
    # Ensure stdout is blocking
    _ensure_blocking_io()
    
    # Extract print kwargs (can't pass them through executor directly)
    sep = kwargs.pop('sep', ' ')
    end = kwargs.pop('end', '\n')
    file = kwargs.pop('file', sys.stdout)
    flush = kwargs.pop('flush', False)
    
    # Build the output string
    output = sep.join(str(arg) for arg in args) + end
    
    # Write to file in executor
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _safe_write, output, file, flush)


def _safe_write(text: str, file, flush: bool):
    """
    Safe write function for executor.
    
    Args:
        text: Text to write
        file: File object to write to
        flush: Whether to flush after writing
    """
    try:
        file.write(text)
        if flush:
            file.flush()
    except Exception as e:
        # If write fails, try stderr as fallback
        try:
            sys.stderr.write(f"Write error: {e}\n")
        except:
            pass