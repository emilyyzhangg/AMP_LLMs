# ============================================================================
# src/amp_llm/network/shell.py
# ============================================================================
"""
Interactive SSH shell implementation.
"""
import asyncio
from colorama import Fore
from amp_llm.config.settings import get_logger

logger = get_logger(__name__)


async def open_interactive_shell(ssh):
    """
    Open interactive remote shell.
    
    Args:
        ssh: AsyncSSH connection object
    """
    print(Fore.GREEN + "✅ Connected to remote host.")
    print(Fore.YELLOW + "Type 'main menu' to return, or 'exit' to close.\n")
    
    try:
        # Open SSH session with PTY
        chan, session = await ssh.open_session(term_type='xterm')
        
        # Request PTY and start shell
        await chan.request_pty(term_type='xterm')
        await chan.exec_shell()
        
        # Create reader task
        async def reader():
            try:
                while True:
                    data = await chan.read(1024)
                    if not data:
                        break
                    print(data, end="", flush=True)
            except Exception as e:
                logger.debug(f"Reader stopped: {e}")
        
        # Start reader in background
        reader_task = asyncio.create_task(reader())
        
        # Interactive input loop
        try:
            while True:
                cmd = input('> ')
                
                if cmd.lower() in ('main menu', 'exit', 'quit'):
                    print(Fore.YELLOW + 'Returning to main menu...')
                    break
                
                await chan.write(cmd + "\n")
                
        except (KeyboardInterrupt, EOFError):
            print(Fore.YELLOW + "\nInterrupted. Returning to menu...")
        finally:
            # Cleanup
            reader_task.cancel()
            try:
                await reader_task
            except asyncio.CancelledError:
                pass
            
            chan.close()
            
    except Exception as e:
        logger.error(f"Shell error: {e}", exc_info=True)
        print(Fore.RED + f"Shell error: {e}")
