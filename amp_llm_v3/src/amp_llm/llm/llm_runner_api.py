# src/amp_llm/llm/llm_runner_api.py
"""
LLM workflow runner using Ollama HTTP API with automatic SSH tunneling.
Uses modular interactive utilities from llm.utils.interactive_utils.
"""
import asyncio
from pathlib import Path
from colorama import Fore, Style
from typing import Optional

from amp_llm.config import get_logger
from amp_llm.llm.utils.session import OllamaSessionManager
from amp_llm.llm.utils.interactive import (
    handle_paste_command,
    handle_load_command,
    list_output_files,
    show_pwd,
)

logger = get_logger(__name__)

try:
    from aioconsole import ainput, aprint
except ImportError:
    async def ainput(prompt: str = ""):
        return input(prompt)
    async def aprint(*args, **kwargs):
        print(*args, **kwargs)


async def run_llm_entrypoint_api(ssh_manager) -> None:
    """
    Main LLM workflow using Ollama HTTP API with automatic SSH tunneling.
    ssh_manager: object that exposes .host and .connection (asyncssh connection)
    """
    await aprint(Fore.CYAN + "=== ⚙️ LLM Workflow (API Mode) ===")
    logger.info("Starting LLM workflow in API mode")

    # host/ssh extraction (fall back to localhost)
    remote_host = getattr(ssh_manager, "host", "localhost")
    ssh_connection = getattr(ssh_manager, "connection", None)

    await aprint(Fore.YELLOW + f"Checking Ollama API at {remote_host}:11434...")

    try:
        # Create session manager (handles direct->tunnel fallback)
        async with OllamaSessionManager(remote_host, 11434, ssh_connection) as session:
            await aprint(Fore.GREEN + "✅ Connected to Ollama!")
            if getattr(session, "_using_tunnel", False):
                await aprint(Fore.CYAN + "   (via SSH tunnel)")

            # List models
            models = await session.list_models()
            if not models:
                await _show_no_models_help(ssh_manager)
                return

            # display models and select
            await aprint(Fore.CYAN + "\nAvailable models:")
            for i, m in enumerate(models, 1):
                await aprint(f" {i}) {m}")

            choice = await ainput(Fore.GREEN + "Select model by number or name (blank to cancel): ")
            choice = choice.strip()
            if not choice:
                await aprint("Cancelled.")
                return

            model = None
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(models):
                    model = models[idx]
            else:
                for m in models:
                    if m.lower() == choice.lower():
                        model = m
                        break

            if not model:
                await aprint(Fore.RED + "Invalid model selection.")
                return

            await aprint(Fore.GREEN + f"\n✅ Using model: {model}")
            await aprint(Fore.CYAN + "\n💡 Commands:")
            await aprint(Fore.CYAN + "   • 'paste' - Enter multi-line paste mode (end with '<<<end')")
            await aprint(Fore.CYAN + "   • 'load <filename>' - Load file content")
            await aprint(Fore.CYAN + "   • 'load <filename> <question>' - Load file and ask question")
            await aprint(Fore.CYAN + "   • 'pwd' - Show current working directory")
            await aprint(Fore.CYAN + "   • 'ls' or 'dir' - List files in output/\n")

            # Chat loop
            while True:
                try:
                    prompt = await ainput(Fore.CYAN + ">>> " + Fore.WHITE)
                    if prompt is None:
                        prompt = ""
                    prompt = prompt.strip()

                    if not prompt:
                        continue

                    if prompt.lower() in ("exit", "quit"):
                        await aprint(Fore.YELLOW + "Exiting LLM workflow...")
                        break
                    if prompt.lower() in ("main menu", "menu"):
                        await aprint(Fore.YELLOW + "Returning to main menu...")
                        break

                    # utility commands
                    if prompt.lower() in ("pwd", "cwd"):
                        await show_pwd(aprint)
                        continue

                    if prompt.lower() in ("ls", "dir", "list"):
                        await list_output_files(aprint)
                        continue

                    if prompt.lower() == "paste":
                        pasted = await handle_paste_command(ainput, aprint)
                        if not pasted:
                            continue
                        prompt_text = pasted
                    elif prompt.lower().startswith("load "):
                        prompt_text = await handle_load_command(prompt, ainput, aprint, logger)
                        if not prompt_text:
                            continue
                    else:
                        prompt_text = prompt

                    # send prompt to Ollama via session
                    await aprint(Fore.YELLOW + f"\n🤔 Sending prompt ({len(prompt_text)} chars) and waiting for response...")
                    try:
                        # session.send_prompt(model, prompt, max_retries...)
                        response = await session.send_prompt(model=model, prompt=prompt_text, max_retries=3)
                        if response.startswith("Error:"):
                            await aprint(Fore.RED + response)
                        else:
                            await aprint(Fore.GREEN + "\n🧠 Response:")
                            await aprint(Fore.WHITE + response + "\n")
                    except Exception as e:
                        await aprint(Fore.RED + f"\n❌ Error: {e}")
                        logger.error(f"API error: {e}", exc_info=True)
                        # attempt reconnect once
                        try:
                            await session.close_session()
                            await session.start_session()
                        except Exception:
                            pass

                except KeyboardInterrupt:
                    await aprint(Fore.YELLOW + "\n\nInterrupted. Type 'exit' to quit.")
                    continue

    except ConnectionError as e:
        await aprint(Fore.RED + f"❌ Connection failed: {e}")
        logger.error(f"Connection error: {e}")
        await _show_connection_help(ssh_manager, remote_host)
    except Exception as e:
        await aprint(Fore.RED + f"❌ Unexpected error: {e}")
        logger.error(f"Unexpected error: {e}", exc_info=True)


# helper UI stubs reused from your previous code
async def _show_no_models_help(ssh_manager):
    await aprint(Fore.RED + "❌ No models found on remote server")
    await aprint(Fore.YELLOW + "Install models using: ollama pull <model_name>")
    await aprint(Fore.CYAN + "\nTroubleshooting:")
    await aprint(Fore.WHITE + "  1. SSH to remote host:")
    if hasattr(ssh_manager, "username") and hasattr(ssh_manager, "host"):
        await aprint(Fore.WHITE + f"     ssh {ssh_manager.username}@{ssh_manager.host}")
    await aprint(Fore.WHITE + "  2. Check Ollama status:")
    await aprint(Fore.WHITE + "     systemctl status ollama")
    await aprint(Fore.WHITE + "  3. List models:")
    await aprint(Fore.WHITE + "     ollama list")
    await aprint(Fore.WHITE + "  4. Pull a base model:")
    await aprint(Fore.WHITE + "     ollama pull llama3.2")


async def _show_connection_help(ssh_manager, remote_host: str):
    await aprint(Fore.RED + "❌ Cannot connect to Ollama")
    await aprint(Fore.CYAN + "\nTroubleshooting:")
    await aprint(Fore.WHITE + "  1. Check if Ollama is running:")
    username = getattr(ssh_manager, "username", "user")
    await aprint(Fore.WHITE + f"     ssh {username}@{remote_host}")
    await aprint(Fore.WHITE + "     systemctl status ollama")
    await aprint(Fore.WHITE + "  2. Test Ollama API:")
    await aprint(Fore.WHITE + "     curl http://localhost:11434/api/tags")
    await aprint(Fore.WHITE + "  3. Start Ollama if not running:")
    await aprint(Fore.WHITE + "     sudo systemctl start ollama")
