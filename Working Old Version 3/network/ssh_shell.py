import threading
import time
import sys
from colorama import Fore, Style


def open_interactive_shell(ssh_client):
    """
    Launch a fully interactive SSH shell session with the remote host.

    Features:
    - Cross-platform (no termios or tty needed)
    - Real-time remote output via background thread
    - Graceful Ctrl+C handling
    - Type 'main menu' or 'exit' to quit and return
    """
    print(Fore.CYAN + "\n=== 🖥️ Interactive Remote Shell ===")
    print(Fore.YELLOW + "(Type 'main menu' or 'exit' to return to main menu)\n" + Style.RESET_ALL)

    # Create a shell channel
    chan = ssh_client.invoke_shell()
    chan.settimeout(0.0)  # Non-blocking read mode

    # --- Remote output reader thread ---
    def _read_from_remote():
        try:
            while True:
                if chan.recv_ready():
                    data = chan.recv(4096).decode(errors="ignore")
                    if not data:
                        break
                    print(data, end="", flush=True)
                elif chan.exit_status_ready():
                    break
                time.sleep(0.05)
        except Exception as e:
            print(Fore.RED + f"\n[⚠️ Remote shell read error: {e}]" + Style.RESET_ALL)
        finally:
            try:
                chan.close()
            except Exception:
                pass

    reader = threading.Thread(target=_read_from_remote, daemon=True)
    reader.start()

    # --- Local input loop ---
    try:
        while True:
            command = input(Fore.GREEN + ">>> " + Style.RESET_ALL)
            cmd_lower = command.strip().lower()

            if cmd_lower in {"exit", "main menu"}:
                print(Fore.MAGENTA + "↩️ Returning to main menu..." + Style.RESET_ALL)
                break

            if not command.strip():
                continue

            try:
                chan.send(command + "\n")
                time.sleep(0.1)
            except Exception as e:
                print(Fore.RED + f"❌ Failed to send command: {e}" + Style.RESET_ALL)
                break

    except KeyboardInterrupt:
        print(Fore.MAGENTA + "\n⛔ Keyboard interrupt detected. Returning to main menu..." + Style.RESET_ALL)

    finally:
        try:
            chan.close()
        except Exception:
            pass
        time.sleep(0.2)
        print(Fore.YELLOW + "✅ SSH shell closed.\n" + Style.RESET_ALL)
