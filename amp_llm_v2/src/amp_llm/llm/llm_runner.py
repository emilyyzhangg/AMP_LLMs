# ============================================================================
# src/amp_llm/network/shell.py
# ============================================================================
"""
Interactive SSH shell implementation (TTY-enabled).
"""
import asyncio
from colorama import Fore
from amp_llm.config import get_logger

logger = get_logger(__name__)


async def detect_remote_shell(ssh):
    """Detect the default remote shell path."""
    try:
        result = await ssh.run("echo $SHELL", check=True)
        shell_path = result.stdout.strip() or "/bin/bash"
        logger.info(f"Detected remote shell: {shell_path}")
        return shell_path
    except Exception:
        logger.warning("Could not detect remote shell; defaulting to bash")
        return "/bin/bash"


async def open_interactive_shell(ssh):
    """
    Open an interactive remote shell with proper prompt handling.
    """
    print(Fore.GREEN + "✅ Connected to remote host.")
    print(Fore.YELLOW + "Type 'exit' or 'main menu' to return.\n")

    shell_path = await detect_remote_shell(ssh)

    try:
        process = await ssh.create_process(
            f"{shell_path} -l",
            term_type="xterm-256color",  # enable full prompt rendering
            encoding="utf-8"
        )

        async def reader():
            """Continuously read and display remote output."""
            try:
                while not process.stdout.at_eof():
                    chunk = await process.stdout.read(1024)
                    if chunk:
                        print(chunk, end='', flush=True)
            except Exception as e:
                logger.debug(f"Reader stopped: {e}")

        reader_task = asyncio.create_task(reader())

        # Send newline to render prompt
        process.stdin.write("\n")
        await process.stdin.drain()

        while True:
            try:
                cmd = await asyncio.get_event_loop().run_in_executor(None, input)
            except EOFError:
                break

            if cmd.strip().lower() in ("exit", "quit", "main menu"):
                print(Fore.YELLOW + "Returning to main menu...")
                break

            process.stdin.write(cmd + "\n")
            await process.stdin.drain()

    except Exception as e:
        logger.error(f"Shell error: {e}", exc_info=True)
        print(Fore.RED + f"Shell error: {e}")
    finally:
        try:
            reader_task.cancel()
            await reader_task
        except:
            pass
        process.terminate()
        await process.wait_closed()
