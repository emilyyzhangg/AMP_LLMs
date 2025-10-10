"""
Fixed SSH and Shell modules - corrected async/await issues.
"""

# ============================================================================
# Updated ssh.py - Add proper connection cleanup
# ============================================================================

import asyncssh
import asyncio
from typing import Optional
from contextlib import asynccontextmanager
from colorama import Fore
from amp_llm.config import get_logger

logger = get_logger(__name__)


class SSHConnection:
    """Wrapper for SSH connection with proper cleanup."""
    
    def __init__(self, connection: asyncssh.SSHClientConnection):
        self.connection = connection
        self._closed = False
    
    async def run(self, *args, **kwargs):
        """Run command on SSH connection."""
        if self._closed:
            raise RuntimeError("Connection is closed")
        return await self.connection.run(*args, **kwargs)
    
    async def close(self):
        """Close connection gracefully."""
        if not self._closed:
            self._closed = True
            try:
                # Close connection with timeout
                await asyncio.wait_for(self._close_connection(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("SSH connection close timeout, forcing close")
                self.connection.abort()
            except Exception as e:
                logger.error(f"Error closing SSH connection: {e}")
    
    async def _close_connection(self):
        """Internal close method."""
        try:
            self.connection.close()
            await self.connection.wait_closed()
        except Exception as e:
            logger.warning(f"Connection close warning: {e}")
    
    def __getattr__(self, name):
        """Proxy other attributes to connection."""
        return getattr(self.connection, name)


async def connect_ssh(
    ip: str,
    username: str,
    password: str,
    keepalive_interval: int = 15,
    keepalive_count_max: int = 3,
    connect_timeout: int = 30
) -> Optional[SSHConnection]:
    """
    Establish SSH connection with keepalive.
    Returns wrapped connection with proper cleanup.
    """
    try:
        logger.info(f"Connecting to {username}@{ip}")
        
        conn = await asyncssh.connect(
            host=ip,
            username=username,
            password=password,
            keepalive_interval=keepalive_interval,
            keepalive_count_max=keepalive_count_max,
            known_hosts=None,
            tcp_keepalive=True,
            client_keys=None,
            connect_timeout=connect_timeout,
            term_type=None,
        )
        
        logger.info(f"Successfully connected to {username}@{ip}")
        return SSHConnection(conn)
        
    except asyncssh.PermissionDenied:
        print(Fore.RED + "❌ Authentication failed.")
        logger.error("SSH authentication failed")
        return None
    except asyncio.TimeoutError:
        print(Fore.RED + f"❌ Connection timeout to {ip}")
        logger.error(f"SSH connection timeout to {ip}")
        return None
    except Exception as e:
        print(Fore.RED + f"❌ SSH connection error: {e}")
        logger.error(f"SSH connection error: {e}", exc_info=True)
        return None


@asynccontextmanager
async def ssh_context(ip: str, username: str, password: str, **kwargs):
    """
    Context manager for SSH connection.
    
    Usage:
        async with ssh_context(ip, user, pass) as ssh:
            await ssh.run("ls")
    """
    connection = await connect_ssh(ip, username, password, **kwargs)
    if connection is None:
        raise ConnectionError("Failed to establish SSH connection")
    
    try:
        yield connection
    finally:
        await connection.close()


# ============================================================================
# FIXED shell.py - Properly handle async input
# ============================================================================

from colorama import Fore
from amp_llm.config import get_logger
from .auto_shell import detect_remote_shell
from .utils import get_remote_user_host

logger = get_logger(__name__)


async def _async_input(prompt: str = "") -> str:
    """
    Async wrapper for input() that can be properly cancelled.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, input, prompt)


async def open_interactive_shell(ssh):
    """
    Open interactive shell with proper cleanup on exit.
    """
    print(Fore.GREEN + "✅ Connected to remote host.")
    print(Fore.YELLOW + "Type 'exit' or 'main menu' to return.\n")

    try:
        # Auto-detect remote shell and get user info
        profile = await detect_remote_shell(ssh)
        user, host = await get_remote_user_host(ssh)
        
        prompt = profile.prompt_fmt.format(user=user, host=host)

        # Interactive loop
        while True:
            try:
                print(Fore.CYAN + prompt, end="", flush=True)
                
                # Use asyncio.wait_for to make input cancellable
                try:
                    line = await asyncio.wait_for(
                        _async_input(),
                        timeout=None  # No timeout, but still cancellable
                    )
                except asyncio.CancelledError:
                    print(Fore.YELLOW + "\nShell cancelled.\n")
                    break

                if line.strip().lower() in ("exit", "quit", "main menu"):
                    print(Fore.YELLOW + "\nReturning to main menu...\n")
                    break

                # Execute command with timeout
                wrapped = _prepare_command(ssh, profile, line)
                
                try:
                    result = await asyncio.wait_for(
                        ssh.run(wrapped, check=False, term_type=None),
                        timeout=30.0
                    )
                    _print_command_output(result)
                except asyncio.TimeoutError:
                    print(Fore.RED + "Command timeout (30s)")
                except asyncio.CancelledError:
                    print(Fore.YELLOW + "\nCommand cancelled.\n")
                    break

            except (KeyboardInterrupt, EOFError):
                print(Fore.YELLOW + "\nInterrupted. Returning to main menu...\n")
                break
            except Exception as e:
                logger.warning(f"Shell error: {e}")
                await asyncio.sleep(0.2)

    except asyncio.CancelledError:
        print(Fore.YELLOW + "\nShell session cancelled.\n")
        raise  # Re-raise to propagate cancellation
    except Exception as e:
        logger.error(f"Shell startup failed: {e}", exc_info=True)
        print(Fore.RED + f"Shell error: {e}")


def _prepare_command(ssh, profile, command: str) -> str:
    """Prepare command with silent wrapper if needed."""
    if hasattr(ssh, "is_connected") and not getattr(ssh, "_term_type", None):
        return command
    return profile.silent_prefix.format(cmd=command)


def _print_command_output(result):
    """Print command stdout and stderr."""
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(Fore.RED + result.stderr.strip())