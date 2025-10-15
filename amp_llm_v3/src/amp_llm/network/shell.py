
import asyncio
from colorama import Fore
from amp_llm.config import get_logger
from amp_llm.cli.async_io import ainput, aprint
from .auto_shell import detect_remote_shell
from .utils import get_remote_user_host

logger = get_logger(__name__)


async def open_interactive_shell(ssh):
    """
    Open interactive shell with proper error handling.
    
    This version properly handles:
    - Non-blocking stdin issues
    - EOF detection
    - Ctrl+C interrupts
    - Command timeouts
    - Task cancellation
    """
    try:
        await aprint(Fore.GREEN + "✅ Connected to remote host.")
        await aprint(Fore.YELLOW + "Type 'exit' or 'main menu' to return.\n")

        # Auto-detect remote shell and get user info
        try:
            profile = await detect_remote_shell(ssh)
            user, host = await get_remote_user_host(ssh)
            logger.info(f"Detected remote shell: {profile.name if hasattr(profile, 'name') else 'unknown'}")
        except Exception as e:
            logger.warning(f"Shell detection failed: {e}")
            # Fallback to simple prompt
            user = "user"
            host = "remote"
            profile = type('Profile', (), {
                'prompt_fmt': '{user}@{host} $ ',
                'silent_prefix': '{cmd}',
                'name': 'bash'
            })()

        # Interactive loop with robust error handling
        consecutive_errors = 0
        max_consecutive_errors = 3
        
        while consecutive_errors < max_consecutive_errors:
            try:
                # Build dynamic prompt
                try:
                    pwd_result = await asyncio.wait_for(
                        ssh.run("pwd", check=False),
                        timeout=2.0
                    )
                    pwd = pwd_result.stdout.strip() if pwd_result.stdout else "~"
                except asyncio.TimeoutError:
                    pwd = "~"
                except Exception:
                    pwd = "~"
                
                # Create prompt
                if hasattr(profile, 'prompt_fmt'):
                    full_prompt = profile.prompt_fmt.format(user=user, host=host)
                    # Add pwd if not in prompt
                    if '{pwd}' not in full_prompt:
                        full_prompt = f"{user}@{host} {pwd} % "
                else:
                    full_prompt = f"{user}@{host}:{pwd}$ "
                
                # Get user input
                try:
                    line = await ainput(Fore.CYAN + full_prompt + Fore.RESET)
                except EOFError:
                    await aprint(Fore.YELLOW + "\nEOF detected. Returning to main menu...")
                    break
                except KeyboardInterrupt:
                    await aprint(Fore.YELLOW + "\n^C")
                    continue
                
                # Reset error counter on successful input
                consecutive_errors = 0
                
                # Check for empty input
                if not line or not line.strip():
                    continue
                
                # Check for exit commands
                if line.strip().lower() in ("exit", "quit", "main menu"):
                    await aprint(Fore.YELLOW + "\nReturning to main menu...")
                    break
                
                # Execute command
                try:
                    wrapped = _prepare_command(profile, line)
                    
                    result = await asyncio.wait_for(
                        ssh.run(wrapped, check=False, term_type=None),
                        timeout=30.0
                    )
                    
                    # Print output
                    _print_command_output(result)
                    
                except asyncio.TimeoutError:
                    await aprint(Fore.RED + "⏱️  Command timeout (30s)")
                except asyncio.CancelledError:
                    await aprint(Fore.YELLOW + "\n⚠️  Command cancelled")
                    raise  # Re-raise to exit loop
                except Exception as cmd_error:
                    await aprint(Fore.RED + f"❌ Command error: {cmd_error}")
                    logger.error(f"Command execution error: {cmd_error}")
                
            except KeyboardInterrupt:
                await aprint(Fore.YELLOW + "\n^C (Type 'exit' to quit)")
                continue
            except EOFError:
                await aprint(Fore.YELLOW + "\nInput stream closed. Returning to main menu...")
                break
            except asyncio.CancelledError:
                await aprint(Fore.YELLOW + "\nShell session cancelled. Returning to main menu...")
                raise
            except Exception as loop_error:
                consecutive_errors += 1
                await aprint(Fore.RED + f"❌ Shell error: {loop_error}")
                logger.error(f"Shell loop error ({consecutive_errors}/{max_consecutive_errors}): {loop_error}")
                
                if consecutive_errors >= max_consecutive_errors:
                    await aprint(Fore.RED + "\n❌ Too many errors. Returning to main menu...")
                    break
                
                # Short delay before retry
                await asyncio.sleep(0.5)
        
        if consecutive_errors >= max_consecutive_errors:
            await aprint(Fore.RED + "Shell terminated due to repeated errors.")
    
    except asyncio.CancelledError:
        await aprint(Fore.YELLOW + "\nShell session cancelled.")
        raise
    except Exception as e:
        await aprint(Fore.RED + f"❌ Shell startup failed: {e}")
        logger.error(f"Shell startup error: {e}", exc_info=True)


def _prepare_command(profile, command: str) -> str:
    """Prepare command with shell wrapper if needed."""
    if hasattr(profile, 'silent_prefix'):
        return profile.silent_prefix.format(cmd=command)
    return command


def _print_command_output(result):
    """Print command stdout and stderr synchronously."""
    if result.stdout:
        output = result.stdout
        if output.endswith('\n'):
            print(output, end='')
        else:
            print(output)
    
    if result.stderr:
        import sys
        print(Fore.RED + result.stderr + Fore.RESET, end='', file=sys.stderr)
        if not result.stderr.endswith('\n'):
            print(file=sys.stderr)