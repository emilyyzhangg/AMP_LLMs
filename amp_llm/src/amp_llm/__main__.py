"""
Main entry point for AMP_LLM application.
"""
import sys
import asyncio
from pathlib import Path

# Add src to path when running directly
src_dir = Path(__file__).parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from colorama import init as colorama_init
colorama_init(autoreset=True)

from config.settings import get_config, get_logger
from core.app import AMPLLMApp  # ← Fixed import

logger = get_logger(__name__)


def print_banner():
    """Print application banner."""
    from colorama import Fore, Style
    
    print(f"\n{Fore.YELLOW}{Style.BRIGHT}{'='*60}")
    print(f"{Fore.YELLOW}AMP_LLM v3.0")
    print(f"{Fore.WHITE}Clinical Trial Research & LLM Integration")
    print(f"{Fore.YELLOW}{'='*60}{Style.RESET_ALL}\n")


async def async_main():
    """Async main entry point."""
    try:
        print_banner()
        
        config = get_config()
        logger.info("Starting AMP_LLM application")
        
        app = AMPLLMApp()
        await app.run()
        
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        print("\n\nApplication terminated by user.")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\nFatal error: {e}")
        sys.exit(1)


def main():
    """Synchronous entry point."""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Failed to start: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()