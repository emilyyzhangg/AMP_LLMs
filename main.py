# main.py
import getpass
from env_setup import setup_environment
from networking import prompt_for_reachable_host  # <-- import it here

def prompt_with_default(prompt_text, default):
    user_input = input(f"{prompt_text} (default: {default}): ").strip()
    return user_input if user_input else default

def main():
    setup_environment()

    from ssh_connection import connect_ssh
    from llm_runner import run_llm_entrypoint

    print("=== SSH Connection Setup ===")

    # Use prompt_for_reachable_host with default IP and limited attempts
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
        # Run the main LLM menu workflow using the established SSH connection
        run_llm_entrypoint(ssh_client)
    except Exception as e:
        print(f"❌ Error during workflow: {e}")
    finally:
        ssh_client.close()
        print("SSH connection closed.")

if __name__ == "__main__":
    main()
