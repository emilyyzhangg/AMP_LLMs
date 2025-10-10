"""
Main entry point for AMP_LLM package when run with python -m amp_llm.
"""
import sys
import asyncio
from pathlib import Path

# Ensure src is in path
src_dir = Path(__file__).parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from colorama import init as colorama_init
colorama_init(autoreset=True)

from amp_llm.config import get_config, get_logger
from amp_llm.config.logging import setup_logging, LogConfig
from amp_llm.core.app import Application

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
        
        # Setup configuration and logging
        config = get_config()
        log_config = LogConfig(
            log_file=config.output.log_file,
            log_level=config.output.log_level,
        )
        setup_logging(log_config)
        
        logger.info("Starting AMP_LLM application")
        
        # Create and run application
        app = Application()
        await app.run()
        
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        print("\n\n✨ Application terminated by user.")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
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