"""
Interactive SSH shell implementation with auto shell detection and echo suppression.
"""

import asyncio
from colorama import Fore
from src.amp_llm.config import get_logger
from src.amp_llm.network.auto_shell import detect_remote_shell

logger = get_logger(__name__)


async def open_interactive_shell(ssh):
    """
    Open a persistent, non-TTY interactive shell session with remote host.
    Automatically detects zsh/bash and disables command echoing.
    """

    print(Fore.GREEN + "✅ Connected to remote host.")
    print(Fore.YELLOW + "Type 'exit' or 'main menu' to return.\n")

    try:
        # Auto-detect remote shell
        profile = await detect_remote_shell(ssh)

        # Get remote username and hostname
        user_result = await ssh.run("whoami", term_type=None, check=False)
        host_result = await ssh.run("hostname", term_type=None, check=False)
        user = (user_result.stdout or "").strip() or "user"
        host = (host_result.stdout or "").strip() or "remote"

        prompt = profile.prompt_fmt.format(user=user, host=host)

        # Interactive loop
        print(Fore.CYAN + prompt, end="", flush=True)

        while True:
            try:
                line = await asyncio.get_event_loop().run_in_executor(None, input)

                if line.strip().lower() in ("exit", "quit", "main menu"):
                    print(Fore.YELLOW + "\nReturning to main menu...\n")
                    break

                # Prepare silent wrapped command
                # Prepare silent wrapped command intelligently
                # Avoid stty if no TTY is available (prevents warnings)
                if hasattr(ssh, "is_connected") and not getattr(ssh, "_term_type", None):
                    wrapped = line  # direct execution, no stty
                else:
                    wrapped = profile.silent_prefix.format(cmd=line)

                result = await ssh.run(wrapped, check=False, term_type=None)

                # Print output cleanly
                if result.stdout:
                    print(result.stdout.strip())

                if result.stderr:
                    print(Fore.RED + result.stderr.strip())

                print(Fore.CYAN + prompt, end="", flush=True)

            except (KeyboardInterrupt, EOFError):
                print(Fore.YELLOW + "\nInterrupted. Returning to main menu...\n")
                break
            except Exception as e:
                logger.warning(f"Shell error: {e}")
                print(Fore.CYAN + prompt, end="", flush=True)
                await asyncio.sleep(0.2)

    except Exception as e:
        logger.error(f"Shell startup failed: {e}", exc_info=True)
        print(Fore.RED + f"Shell error: {e}")
