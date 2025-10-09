"""
Main entry point for AMP_LLM application.
Uses aioconsole for non-blocking async input and proper signal handling.
Auto-installs dependencies from requirements.txt and manages virtual environment.
Updated with API mode for Ollama to avoid terminal fragmentation.

FIXED: Import order - env_setup runs FIRST, before any module imports.
"""
import sys
import os

# CRITICAL: Ensure environment FIRST, before any other imports
# This may restart Python in the virtual environment
from env_setup import ensure_env
ensure_env()

# ============================================================================
# NOW safe to import everything else (we're in venv with packages installed)
# ============================================================================

import asyncio
import signal
from typing import Optional
from colorama import init, Fore, Style

init(autoreset=True)

# Import project modules (after env is confirmed)
from config import get_config, get_logger

logger = get_logger(__name__)
config = get_config()

# Import async modules
try:
    from aioconsole import ainput, aprint
except ImportError:
    print(Fore.RED + "❌ Failed to import aioconsole after environment setup")
    print(Fore.YELLOW + "Please run: pip install -r requirements.txt")
    sys.exit(1)

from network.async_networking import ping_host
from network.ssh_connection import connect_ssh
from network.ssh_shell import open_interactive_shell
from llm.async_llm_runner import run_llm_entrypoint
from llm.async_llm_runner_api import run_llm_entrypoint_api
from data.async_nct_lookup import run_nct_lookup

# Import research assistant AFTER all dependencies are confirmed
from llm.ct_research_runner import run_ct_research_assistant


class GracefulExit(SystemExit):
    """Custom exception for graceful exit."""
    pass


class AMPLLMApp:
    """Main application class with proper lifecycle management."""
    
    def __init__(self):
        self.ssh_connection: Optional[object] = None
        self.ssh_ip: Optional[str] = None
        self.ssh_username: Optional[str] = None
        self.running = True
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """Setup handlers for graceful shutdown on SIGINT/SIGTERM."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self.running = False
            raise GracefulExit()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def cleanup(self):
        """Cleanup resources on exit."""
        if self.ssh_connection:
            try:
                logger.info("Closing SSH connection...")
                self.ssh_connection.close()
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Error closing SSH: {e}")
    
    async def ensure_connected(self):
        """Check if SSH is still connected, reconnect if needed."""
        try:
            if self.ssh_connection and not self.ssh_connection.is_closed():
                return True
        except:
            pass
        
        logger.warning("SSH connection lost, attempting reconnect...")
        await aprint(Fore.YELLOW + "⚠️  SSH connection lost, reconnecting...")
        
        success = await self.reconnect_ssh()
        if success:
            await aprint(Fore.GREEN + "✅ Reconnected!")
            return True
        else:
            await aprint(Fore.RED + "❌ Reconnection failed")
            return False
    
    async def reconnect_ssh(self) -> bool:
        """Attempt to reconnect SSH using stored credentials."""
        if not self.ssh_ip or not self.ssh_username:
            await aprint(Fore.RED + "❌ No previous connection info available.")
            return False
        
        await aprint(Fore.YELLOW + f"Reconnecting to {self.ssh_username}@{self.ssh_ip}...")
        
        if self.ssh_connection:
            try:
                self.ssh_connection.close()
            except Exception:
                pass
        
        self.ssh_connection = await self.prompt_password_and_connect(
            self.ssh_username, 
            self.ssh_ip
        )
        
        return self.is_ssh_connected()
    
    def is_ssh_connected(self) -> bool:
        """Check if SSH connection is active."""
        if not self.ssh_connection:
            return False
        try:
            return not self.ssh_connection.is_closed()
        except AttributeError:
            return True
    
    async def prompt_ip(self) -> str:
        """Prompt for IP address with validation and ping check."""
        default = config.network.default_ip
        
        while self.running:
            try:
                ip = await ainput(
                    Fore.CYAN + f"Enter remote host IP [{default}]: " + Style.RESET_ALL
                )
                ip = ip.strip() or default
                
                await aprint(Fore.YELLOW + f"Pinging {ip}...")
                ok = await ping_host(ip, timeout=config.network.ping_timeout)
                
                if ok:
                    await aprint(Fore.GREEN + f"✅ Successfully reached {ip}")
                    logger.info(f"Connected to {ip}")
                    return ip
                
                await aprint(Fore.RED + f"❌ Could not reach {ip}. Try again.")
                logger.warning(f"Failed to ping {ip}")
                
            except GracefulExit:
                raise
            except Exception as e:
                logger.error(f"Error in IP prompt: {e}")
                await aprint(Fore.RED + f"Error: {e}")
        
        raise GracefulExit()
    
    async def prompt_username(self) -> str:
        """Prompt for SSH username."""
        default = config.network.default_username
        
        try:
            username = await ainput(
                Fore.CYAN + f"Enter SSH username [{default}]: " + Style.RESET_ALL
            )
            return username.strip() or default
        except GracefulExit:
            raise
        except Exception as e:
            logger.error(f"Error in username prompt: {e}")
            return default
    
    async def prompt_password_and_connect(self, username: str, ip: str) -> object:
        """Prompt for password and establish SSH connection."""
        import getpass
        
        attempt = 0
        
        while self.running and attempt < config.network.max_auth_attempts:
            try:
                await aprint(Fore.CYAN + f"Enter SSH password for {username}@{ip}: ", end='')
                password = getpass.getpass('')
                
                await aprint(Fore.YELLOW + "Connecting...")
                ssh = await connect_ssh(ip, username, password)
                
                if ssh:
                    await aprint(Fore.GREEN + f"✅ Successfully connected to {username}@{ip}")
                    logger.info(f"SSH connection established: {username}@{ip}")
                    self.ssh_ip = ip
                    self.ssh_username = username
                    return ssh
                
                attempt += 1
                remaining = config.network.max_auth_attempts - attempt
                
                if remaining > 0:
                    await aprint(
                        Fore.RED + 
                        f"❌ Authentication failed. {remaining} attempt(s) remaining."
                    )
                else:
                    await aprint(Fore.RED + "❌ Max authentication attempts reached.")
                    raise GracefulExit()
                
            except GracefulExit:
                raise
            except Exception as e:
                logger.error(f"Connection error: {e}")
                await aprint(Fore.RED + f"Error: {e}")
                attempt += 1
        
        raise GracefulExit()
    
    async def main_menu(self):
        """Main menu loop with proper async handling."""
        while self.running:
            try:
                await aprint(Fore.YELLOW + Style.BRIGHT + "\n=== 🧠 AMP_LLM Main Menu ===")
                await aprint(Fore.CYAN + "1." + Fore.WHITE + " Interactive Shell")
                await aprint(Fore.CYAN + "2." + Fore.WHITE + " LLM Workflow (API Mode)")
                await aprint(Fore.CYAN + "3." + Fore.WHITE + " LLM Workflow (SSH Terminal)")
                await aprint(Fore.CYAN + "4." + Fore.WHITE + " NCT Lookup")
                await aprint(Fore.CYAN + "5." + Fore.WHITE + " Clinical Trial Research Assistant " + Fore.GREEN + "← NEW!")
                await aprint(Fore.CYAN + "6." + Fore.WHITE + " Exit")
                
                choice = await ainput(Fore.GREEN + "\nSelect an option (1-6): ")
                choice = choice.strip().lower()
                
                if choice in ("1", "interactive", "shell"):
                    logger.info("User selected: Interactive Shell")
                    await open_interactive_shell(self.ssh_connection)
                
                elif choice in ("2", "llm", "api"):
                    logger.info("User selected: LLM Workflow (API)")
                    await run_llm_entrypoint_api(self.ssh_connection)
                
                elif choice in ("3", "terminal", "ssh"):
                    logger.info("User selected: LLM Workflow (SSH Terminal)")
                    await run_llm_entrypoint(self.ssh_connection)
                
                elif choice in ("4", "nct", "lookup"):
                    logger.info("User selected: NCT Lookup")
                    await run_nct_lookup()
                
                elif choice in ("5", "research", "assistant"):
                    logger.info("User selected: Clinical Trial Research Assistant")
                    await run_ct_research_assistant(self.ssh_connection)
            
                elif choice in ("6", "exit", "quit"):
                    await aprint(Fore.MAGENTA + "👋 Exiting. Goodbye!")
                    break
                
                else:
                    await aprint(Fore.RED + "❌ Invalid option. Please choose 1-6.")
                
            except GracefulExit:
                break
            except Exception as e:
                logger.error(f"Error in main menu: {e}", exc_info=True)
                await aprint(Fore.RED + f"An error occurred: {e}")
                await aprint(Fore.YELLOW + "Returning to main menu...")
    
    async def run(self):
        """Main application entry point."""
        try:
            await aprint(Fore.YELLOW + Style.BRIGHT + "\n=== 🚀 AMP_LLM v2.0 ===")
            await aprint(Fore.WHITE + "Clinical Trial Research & LLM Integration Tool\n")
            
            await aprint(Fore.YELLOW + "\n=== 🔐 SSH Connection Setup ===")
            
            ip = await self.prompt_ip()
            username = await self.prompt_username()
            
            self.ssh_connection = await self.prompt_password_and_connect(username, ip)
            
            await self.main_menu()
            
        except GracefulExit:
            logger.info("Graceful exit initiated")
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            await aprint(Fore.YELLOW + "\n\nShutting down gracefully...")
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            await aprint(Fore.RED + f"Fatal error: {e}")
        finally:
            await self.cleanup()


async def main():
    """Application entry point wrapper."""
    app = AMPLLMApp()
    await app.run()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Application terminated by user.")
    except Exception as e:
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        print(f"❌ Fatal error: {e}")
        sys.exit(1)