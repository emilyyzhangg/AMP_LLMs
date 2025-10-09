"""
Main entry point for AMP_LLM application.
Uses aioconsole for non-blocking async input and proper signal handling.
Auto-installs dependencies from requirements.txt and manages virtual environment.
Updated with API mode for Ollama to avoid terminal fragmentation.
"""
import asyncio
import signal
import sys
import os
from typing import Optional
from colorama import init, Fore, Style
from llm.ct_research_runner import run_ct_research_assistant

init(autoreset=True)

# Ensure environment before imports
from env_setup import ensure_env
ensure_env()

# Now try imports, install from requirements.txt if missing
def ensure_packages_from_requirements():
    """Ensure all required packages from requirements.txt are installed."""
    import importlib.util
    import subprocess
    from pathlib import Path
    
    # Package import name mapping (some packages have different import names)
    PACKAGE_IMPORT_MAPPING = {
        'asyncssh': 'asyncssh',
        'aiohttp': 'aiohttp',
        'aioconsole': 'aioconsole',
        'colorama': 'colorama',
        'python-dotenv': 'dotenv',
        'openai': 'openai',
    }
    
    requirements_file = Path(__file__).parent / 'requirements.txt'
    
    if not requirements_file.exists():
        print(Fore.RED + f"❌ requirements.txt not found at {requirements_file}")
        print(Fore.YELLOW + "Creating basic requirements.txt...")
        with open(requirements_file, 'w') as f:
            f.write("asyncssh>=2.14.0\n")
            f.write("aiohttp>=3.9.0\n")
            f.write("aioconsole>=0.7.0\n")
            f.write("colorama>=0.4.6\n")
            f.write("python-dotenv>=1.0.0\n")
            f.write("openai>=1.0.0\n")
        print(Fore.GREEN + "✅ Created requirements.txt\n")
    
    # Parse requirements.txt
    required_packages = {}
    with open(requirements_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Extract package name (before any version specifier)
            pkg_name = line.split('>=')[0].split('==')[0].split('<=')[0].split('>')[0].split('<')[0].strip()
            
            # Get import name
            import_name = PACKAGE_IMPORT_MAPPING.get(pkg_name, pkg_name)
            required_packages[import_name] = pkg_name
    
    # Check which packages are missing
    missing = []
    for import_name, package_name in required_packages.items():
        if importlib.util.find_spec(import_name) is None:
            missing.append(package_name)
    
    if missing:
        print(Fore.YELLOW + f"Installing {len(missing)} missing package(s) from requirements.txt...")
        try:
            # Install all at once from requirements.txt
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", "-r", str(requirements_file)
            ])
            print(Fore.GREEN + "✅ All packages installed successfully!\n")
        except subprocess.CalledProcessError as e:
            print(Fore.RED + f"❌ Failed to install packages: {e}")
            print(Fore.YELLOW + "\nTrying to install missing packages individually...")
            for pkg in missing:
                print(Fore.CYAN + f"  Installing {pkg}...")
                try:
                    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
                    print(Fore.GREEN + f"  ✅ {pkg} installed")
                except subprocess.CalledProcessError as e:
                    print(Fore.RED + f"  ❌ Failed to install {pkg}: {e}")
                    sys.exit(1)

ensure_packages_from_requirements()

# Now import everything else
from config import get_config, get_logger

logger = get_logger(__name__)
config = get_config()

from aioconsole import ainput, aprint
from network.async_networking import ping_host
from network.ssh_connection import connect_ssh
from network.ssh_shell import open_interactive_shell
from llm.async_llm_runner import run_llm_entrypoint
from llm.async_llm_runner_api import run_llm_entrypoint_api
from data.async_nct_lookup import run_nct_lookup


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
                await asyncio.sleep(0.1)  # Give connection time to close
            except Exception as e:
                logger.error(f"Error closing SSH: {e}")
                # In main.py, add this method to AMPLLMApp class:

    async def ensure_connected(self):
        """Check if SSH is still connected, reconnect if needed."""
        try:
            if self.ssh_connection and not self.ssh_connection.is_closed():
                return True
        except:
            pass
        
        # Connection is dead, try to reconnect
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
        
        # Close old connection if exists
        if self.ssh_connection:
            try:
                self.ssh_connection.close()
            except Exception:
                pass
        
        # Reconnect
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
            return True  # Assume connected if no is_closed method
    
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
                # Use getpass for hidden password input
                # Note: This blocks briefly but is acceptable for password entry
                await aprint(Fore.CYAN + f"Enter SSH password for {username}@{ip}: ", end='')
                password = getpass.getpass('')
                
                await aprint(Fore.YELLOW + "Connecting...")
                ssh = await connect_ssh(ip, username, password)
                
                if ssh:
                    await aprint(Fore.GREEN + f"✅ Successfully connected to {username}@{ip}")
                    logger.info(f"SSH connection established: {username}@{ip}")
                    # Store connection info
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
                    await aprint(Fore.RED + "❌ Invalid option. Please choose 1-5.")
                
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
            
            # Get connection details
            ip = await self.prompt_ip()
            username = await self.prompt_username()
            
            # Establish connection
            self.ssh_connection = await self.prompt_password_and_connect(username, ip)
            
            # Run main menu
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