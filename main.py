import os
import sys
import getpass
from colorama import init, Fore, Style

# --- Run environment setup before anything else ---
from env_setup import ensure_env
ensure_env()

# After env is set, we can safely import these
import paramiko
from network.networking import ping_host
from network.ssh_connection import connect_ssh
from network.ssh_shell import open_interactive_shell
from llm.llm_runner import run_llm_entrypoint
from data.nct_lookup import run_nct_lookup

# Initialize colorama
init(autoreset=True)


# ===============================
# Utility Input Helpers
# ===============================

def prompt_ip():
    """Prompt user for IP and verify connectivity."""
    default_ip = "100.99.162.98"
    while True:
        ip = input(Fore.CYAN + f"Enter remote host IP [{default_ip}]: " + Style.RESET_ALL).strip() or default_ip
        if ping_host(ip):
            print(Fore.GREEN + f"✅ Successfully reached {ip}")
            return ip
        print(Fore.RED + f"❌ Could not reach {ip}. Try again.")


def prompt_username():
    """Prompt for SSH username."""
    default_user = "emilyzhang"
    username = input(Fore.CYAN + f"Enter SSH username [{default_user}]: " + Style.RESET_ALL).strip() or default_user
    return username


def prompt_password(username, ip):
    """Prompt for SSH password (retries automatically on failure)."""
    while True:
        password = getpass.getpass(Fore.CYAN + f"Enter SSH password for {username}@{ip}: " + Style.RESET_ALL)
        ssh = connect_ssh(ip, username, password)
        if ssh:
            print(Fore.GREEN + f"✅ Successfully connected to {username}@{ip}")
            return ssh
        print(Fore.RED + "❌ Incorrect password. Please try again.\n")


# ===============================
# Main Menu Logic
# ===============================

def main_menu(ssh):
    """Main interactive AMP_LLM menu loop."""
    while True:
        print(Fore.YELLOW + Style.BRIGHT + "\n=== 🧠 AMP_LLM Main Menu ===")
        print(Fore.CYAN + "1." + Fore.WHITE + " Interactive Shell")
        print(Fore.CYAN + "2." + Fore.WHITE + " LLM Workflow")
        print(Fore.CYAN + "3." + Fore.WHITE + " NCT Lookup")
        print(Fore.CYAN + "4." + Fore.WHITE + " Exit")

        choice = input(Fore.GREEN + "\nSelect an option (1-4): " + Style.RESET_ALL).strip().lower()

        # --- Interactive Shell ---
        if choice in ("1", "interactive", "shell"):
            open_interactive_shell(ssh)

        # --- LLM Workflow ---
        elif choice in ["2", "llm", "workflow"]:
            print(Fore.CYAN + "\n=== ⚙️ LLM Workflow ===")
            run_llm_entrypoint(ssh)

        # --- NCT Lookup ---
        elif choice in ("3", "nct", "lookup"):
            run_nct_lookup()

        # --- Exit ---
        elif choice in ("4", "exit", "quit"):
            print(Fore.MAGENTA + "👋 Exiting program. Goodbye!")
            try:
                ssh.close()
            except Exception:
                pass
            sys.exit(0)

        else:
            print(Fore.RED + "⚠️ Invalid option. Please choose 1–4.")


# ===============================
# Main Control Flow
# ===============================

def main():
    """Program entry point."""
    print(Fore.YELLOW + "\n=== 🔐 SSH Connection Setup ===")
    ip = prompt_ip()
    username = prompt_username()

    # Loop until correct password
    ssh = prompt_password(username, ip)

    # Directly launch main menu after successful connection
    main_menu(ssh)


if __name__ == "__main__":
    main()
