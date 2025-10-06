import os
import sys

# --- Run env setup before anything else ---
from env_setup import ensure_env
ensure_env()

# Now safe to import modules that rely on pip-installed packages
import getpass
import subprocess
from colorama import init, Fore, Style
import paramiko

from network.networking import ping_host
from network.ssh_connection import connect_ssh
from llm.llm_runner import run_llm_entrypoint
from data.nct_lookup import run_nct_lookup
from llm.interactive import interactive_session


# Initialize colorama
init(autoreset=True)


def prompt_ip():
    """Prompt for IP and verify connectivity."""
    default_ip = "100.99.162.98"
    while True:
        ip = input(Fore.CYAN + f"Enter remote host IP [{default_ip}]: ").strip() or default_ip
        if ping_host(ip):
            print(Fore.GREEN + f"✅ Successfully reached {ip}")
            return ip
        print(Fore.RED + f"❌ Could not reach {ip}. Try again.")


def prompt_username():
    """Prompt for SSH username."""
    default_user = "emilyzhang"
    username = input(Fore.CYAN + f"Enter SSH username [{default_user}]: ").strip() or default_user
    return username


def main_menu(ssh):
    """Display the main menu loop."""
    while True:
        print(Fore.YELLOW + Style.BRIGHT + "\n=== 🧠 AMP_LLM Main Menu ===")
        print(Fore.CYAN + "1." + Fore.WHITE + " Interactive Shell")
        print(Fore.CYAN + "2." + Fore.WHITE + " LLM Workflow")
        print(Fore.CYAN + "3." + Fore.WHITE + " NCT Lookup")
        print(Fore.CYAN + "4." + Fore.WHITE + " Exit")

        choice = input(Fore.GREEN + "\nSelect an option (1-4): " + Style.RESET_ALL).strip().lower()

        if choice in ("1", "interactive", "shell"):
            interactive_session(ssh)
        elif choice in ("2", "llm", "workflow"):
            run_llm_entrypoint()
        elif choice in ("3", "nct", "lookup"):
            run_nct_lookup()
        elif choice in ("4", "exit", "quit"):
            print(Fore.MAGENTA + "👋 Exiting program. Goodbye!")
            try:
                ssh.close()
            except Exception:
                pass
            sys.exit(0)
        else:
            print(Fore.RED + "⚠️ Invalid option. Please choose 1–4.")


def main():
    """Top-level control flow."""
    print(Fore.YELLOW + "\n=== 🔐 SSH Connection Setup ===")
    ip = prompt_ip()
    username = prompt_username()

    ssh = connect_ssh(ip, username)
    if not ssh:
        print(Fore.RED + "❌ SSH connection could not be established.")
        sys.exit(1)

    main_menu(ssh)


if __name__ == "__main__":
    main()
