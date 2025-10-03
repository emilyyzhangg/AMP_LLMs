import getpass
from env_setup import setup_environment   # This can be imported early

def prompt_with_default(prompt_text, default):
    user_input = input(f"{prompt_text} (default: {default}): ").strip()
    return user_input if user_input else default

def main():
    # --- Setup environment first ---
    setup_environment()

    # --- Now import modules that depend on installed packages ---
    from ssh_connection import connect_ssh
    from llm_runner import run_llm_workflow

    print("=== SSH Connection Setup ===")
    host = prompt_with_default("Enter SSH host", "100.99.162.98")

    port_input = prompt_with_default("Enter SSH port", "22")
    try:
        port = int(port_input)
    except ValueError:
        print("Invalid port number. Using default 22.")
        port = 22

    username = prompt_with_default("Enter SSH username", "emilyzhang")

    password = getpass.getpass("Enter SSH password: ")

    print(f"Connecting to {username}@{host}:{port} ...")
    ssh_client = connect_ssh(host, port, username, password)
    if ssh_client is None:
        print("Failed to connect via SSH. Exiting.")
        return

    try:
        run_llm_workflow(ssh_client)
    except Exception as e:
        print(f"An error occurred during the LLM workflow: {e}")
    finally:
        ssh_client.close()
        print("SSH connection closed.")

if __name__ == "__main__":
    main()
