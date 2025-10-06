import asyncio
from colorama import init, Fore, Style
init(autoreset=True)

# ensure env before heavy imports
from env_setup import ensure_env
ensure_env()

import getpass
from network.async_networking import ping_host
from network.ssh_connection import connect_ssh
from network.ssh_shell import open_interactive_shell
from llm.async_llm_runner import run_llm_entrypoint
from data.async_nct_lookup import run_nct_lookup

async def prompt_ip():
    default = "100.99.162.98"
    while True:
        ip = input(Fore.CYAN + f"Enter remote host IP [{default}]: " + Style.RESET_ALL).strip() or default
        ok = await ping_host(ip)
        if ok:
            print(Fore.GREEN + f"✅ Successfully reached {ip}")
            return ip
        print(Fore.RED + f"❌ Could not reach {ip}. Try again.")

def prompt_username():
    default = "emilyzhang"
    return input(Fore.CYAN + f"Enter SSH username [{default}]: " + Style.RESET_ALL).strip() or default

async def prompt_password_and_connect(username, ip):
    while True:
        password = getpass.getpass(Fore.CYAN + f"Enter SSH password for {username}@{ip}: " + Style.RESET_ALL)
        ssh = await connect_ssh(ip, username, password)
        if ssh:
            print(Fore.GREEN + f"✅ Successfully connected to {username}@{ip}")
            return ssh
        print(Fore.RED + "❌ Authentication failed — try again.")

async def main_menu(ssh):
    while True:
        print(Fore.YELLOW + Style.BRIGHT + "\n=== 🧠 AMP_LLM Main Menu ===")
        print(Fore.CYAN + "1." + Fore.WHITE + " Interactive Shell")
        print(Fore.CYAN + "2." + Fore.WHITE + " LLM Workflow")
        print(Fore.CYAN + "3." + Fore.WHITE + " NCT Lookup")
        print(Fore.CYAN + "4." + Fore.WHITE + " Exit")
        choice = input(Fore.GREEN + "\nSelect an option (1-4): " + Style.RESET_ALL).strip().lower()
        if choice in ("1","interactive","shell"):
            await open_interactive_shell(ssh)
        elif choice in ("2","llm","workflow"):
            await run_llm_entrypoint(ssh)
        elif choice in ("3","nct","lookup"):
            await run_nct_lookup()
        elif choice in ("4","exit","quit"):
            print(Fore.MAGENTA + "👋 Exiting. Closing SSH...")
            try:
                ssh.close()
            except Exception:
                pass
            return
        else:
            print(Fore.RED + "Invalid option.")

async def main():
    print(Fore.YELLOW + "\n=== 🔐 SSH Connection Setup ===")
    ip = await prompt_ip()
    user = prompt_username()
    ssh = await prompt_password_and_connect(user, ip)
    await main_menu(ssh)

if __name__ == '__main__':
    asyncio.run(main())
