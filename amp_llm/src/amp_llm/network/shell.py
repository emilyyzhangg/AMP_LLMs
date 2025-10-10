"""
Interactive SSH shell implementation.
"""
import asyncio
import sys
from colorama import Fore
from amp_llm.config import get_logger

logger = get_logger(__name__)


async def open_interactive_shell(ssh):
    """
    Open interactive remote shell.
    
    Args:
        ssh: AsyncSSH connection object
    """
    print(Fore.GREEN + "✅ Connected to remote host.")
    print(Fore.YELLOW + "Type 'exit' or 'main menu' to return.\n")
    
    try:
        # Start interactive process
        process = await ssh.create_process(
            'bash -l',
            term_type='xterm',
            encoding='utf-8'
        )
        
        # Create reader task
        async def reader():
            """Read and display output from remote."""
            try:
                while True:
                    chunk = await process.stdout.read(1024)
                    if not chunk:
                        break
                    print(chunk, end='', flush=True)
            except Exception as e:
                logger.debug(f"Reader stopped: {e}")
        
        # Start reader in background
        reader_task = asyncio.create_task(reader())
        
        # Interactive input loop
        try:
            # Send initial newline to show prompt
            process.stdin.write('\n')
            await process.stdin.drain()
            
            while True:
                # Read user input
                try:
                    line = await asyncio.get_event_loop().run_in_executor(
                        None, input
                    )
                except EOFError:
                    break
                
                # Check for exit commands
                if line.strip().lower() in ('exit', 'quit', 'main menu'):
                    print(Fore.YELLOW + 'Returning to main menu...')
                    break
                
                # Send to remote
                process.stdin.write(line + '\n')
                await process.stdin.drain()
                
        except (KeyboardInterrupt, EOFError):
            print(Fore.YELLOW + "\n\nInterrupted. Returning to menu...")
        finally:
            # Cleanup
            reader_task.cancel()
            try:
                await reader_task
            except asyncio.CancelledError:
                pass
            
            try:
                process.stdin.close()
                process.terminate()
                await process.wait_closed()
            except:
                pass
            
    except Exception as e:
        logger.error(f"Shell error: {e}", exc_info=True)
        print(Fore.RED + f"Shell error: {e}")