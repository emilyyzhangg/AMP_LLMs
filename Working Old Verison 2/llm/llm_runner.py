# llm/llm_runner.py

import getpass
from data.data_fetchers import fetch_clinical_trial_and_pubmed_pmc
from llm.interactive import interactive_session
from llm.llm_utils import list_local_models, choose_model
from network.ssh_connection import connect_ssh, prompt_for_reachable_host


def run_llm_entrypoint(ssh_client=None):
    models = list_local_models()
    model = choose_model(models)
    print(f"Using model: {model}")

    print("1) Interactive")
    print("2) Exit")
    choice = input("Select: ").strip()
    if choice == "1":
        interactive_session(ssh_client=ssh_client, model_name=model)
    else:
        print("Exiting.")


def main_connect_then_run():
    use_remote = input("Use remote Ollama (SSH)? (y/N): ").strip().lower() == "y"
    ssh_client = None
    if use_remote:
        host = prompt_for_reachable_host()
        username = input(f"SSH username (default: {getpass.getuser()}): ").strip() or getpass.getuser()
        ssh_client = connect_ssh(host, username)
        if not ssh_client:
            print("SSH connection failed.")
            return
    try:
        run_llm_entrypoint(ssh_client=ssh_client)
    finally:
        if ssh_client:
            ssh_client.close()
            print("SSH connection closed.")


if __name__ == "__main__":
    main_connect_then_run()
