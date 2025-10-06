# amphoraxe/main.py

import getpass
from env_setup import setup_environment
from network.networking import prompt_for_reachable_host

def prompt_with_default(prompt_text, default):
    user_input = input(f"{prompt_text} (default: {default}): ").strip()
    return user_input if user_input else default

def main():
    # Step 1: Ensure environment is set up (venv + packages)
    setup_environment()
    print("✅ Environment setup complete.\n")

    # Step 2: Import modules after env is ready to avoid import errors
    from network.ssh_connection import connect_ssh
    from llm.llm_runner import run_llm_entrypoint

    print("=== SSH Connection Setup ===")

    # Prompt for host with default and reachability check
    host = prompt_for_reachable_host(default_host="100.99.162.98", max_attempts=1, timeout=1000)
    if host is None:
        print("❌ No reachable host provided. Exiting.")
        return

    port = int(prompt_with_default("Enter SSH port", "22"))
    username = prompt_with_default("Enter SSH username", "emilyzhang")
    password = getpass.getpass("Enter SSH password: ")

    print(f"Connecting to {username}@{host}:{port} ...")
    ssh_client = connect_ssh(host, port, username, password)
    if ssh_client is None:
        print("❌ SSH connection failed. Exiting.")
        return

    try:
        run_llm_entrypoint(ssh_client)
    except KeyboardInterrupt:
        print("\n⏹️ Interrupted by user. Exiting...")
    except Exception as e:
        print(f"❌ Error during workflow: {e}")
    finally:
        if ssh_client:
            ssh_client.close()
            print("SSH connection closed.")

if __name__ == "__main__":
    main()
