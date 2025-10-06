# llm_runner.py
import os
import sys
import json
import getpass
from data.data_fetchers import fetch_clinical_trial_and_pubmed_pmc
from llm.llm_utils import (
    list_local_models,
    run_ollama_local_with_file,
    choose_model
)
from llm.interactive import interactive_session
from network.networking import prompt_for_reachable_host
from network.ssh_connection import connect_ssh


def prompt_nct_number():
    """
    Prompt user to enter a valid NCT number or exit commands.
    """
    while True:
        nct = input("Enter NCT number (or 'exit'/'main menu' to go back): ").strip()
        if nct.lower() in ["exit", "main menu"]:
            return None
        nct_upper = nct.upper()
        if nct_upper.startswith("NCT") and len(nct_upper) > 3:
            return nct_upper
        print("Invalid NCT number format. Please enter again (e.g. NCT04043065).")


def prompt_action():
    """
    Present user with possible actions and return their choice.
    """
    print("\nChoose an action:")
    print("1. Dump clinical trial data to text file")
    print("2. Enter new NCT number")
    print("3. Start Ollama LLM with saved file")
    print("4. Return to main menu")
    return input("Enter choice (1-4): ").strip()


def prompt_ssh_credentials():
    """
    Prompt the user for SSH credentials securely.

    Returns:
        tuple(host, port, username, password)
    """
    host = prompt_for_reachable_host()
    if not host:
        return None, None, None, None

    port_str = input("Enter SSH port (default 22): ").strip()
    port = int(port_str) if port_str.isdigit() else 22

    username = input("Enter SSH username: ").strip()
    # Use getpass to hide password input on console
    password = getpass.getpass("Enter SSH password: ")

    return host, port, username, password


def run_llm_entrypoint(ssh_client=None):
    """
    Main entry point to run the LLM workflow and interactive SSH sessions.
    """
    ollama_path = "/opt/homebrew/bin/ollama"  # Adjust if needed
    print(f"Ollama path: {ollama_path}")

    while True:
        print("\n=== Main Menu ===")
        print("1. Interactive SSH shell")
        print("2. Run ClinicalTrials + PubMed + Ollama workflow")
        print("3. Exit")
        choice = input("Choose option (1/2/3): ").strip()

        if choice == "1":
            # Prompt user for SSH credentials and connect
            print("\n🌟 Setting up SSH connection for interactive session 🌟")
            host, port, username, password = prompt_ssh_credentials()

            if not host:
                print("SSH setup aborted. Returning to main menu.")
                continue

            ssh_client = connect_ssh(host, port, username, password)
            if not ssh_client:
                print("Failed to connect via SSH. Returning to main menu.")
                continue

            # Choose model for interactive session
            model_name = input("Enter Ollama model name (or press Enter for default): ").strip()
            if not model_name:
                model_name = "llama2"  # or any default model you prefer

            # Run interactive session with SSH client and model name
            interactive_session(ssh_client=ssh_client, model_name=model_name)

            # Close SSH connection cleanly
            ssh_client.close()
            print("SSH connection closed. Returning to main menu.")

        elif choice == "2":
            while True:
                nct = prompt_nct_number()
                if nct is None:
                    print("Returning to main menu.")
                    break

                print(f"Fetching data for {nct}...")
                data = fetch_clinical_trial_and_pubmed_pmc(nct)
                if "error" in data:
                    print(f"Error: {data['error']}")
                    continue

                print(f"\nFull Clinical Trial + PubMed Data for {nct}:\n")
                print(json.dumps(data, indent=4, sort_keys=True))

                while True:
                    action = prompt_action()

                    if action == "1":
                        filename = f"{nct}.txt"
                        try:
                            with open(filename, "w", encoding="utf-8") as f:
                                json.dump(data, f, indent=4, sort_keys=True)
                            print(f"Data saved to '{filename}'.")
                        except Exception as e:
                            print(f"Write error: {e}")

                    elif action == "2":
                        break  # Re-prompt NCT

                    elif action == "3":
                        filename = f"{nct}.txt"
                        if not os.path.isfile(filename):
                            print(f"File '{filename}' not found. Please save it first (option 1).")
                            continue

                        models = list_local_models(ollama_path)
                        if not models:
                            print("No models found.")
                            continue

                        selected_model = choose_model(models)
                        if selected_model in [None, "main_menu"]:
                            break

                        run_ollama_local_with_file(ollama_path, selected_model, filename)

                    elif action == "4":
                        break

                    else:
                        print("Invalid choice. Please enter 1, 2, 3, or 4.")

                if action == "4":
                    break

        elif choice == "3":
            print("Goodbye.")
            sys.exit(0)

        else:
            print("Invalid choice. Please enter 1, 2, or 3.")


# from llm_utils import check_ollama_installed, get_available_models, ensure_model_available
# def run_llm_workflow(ssh_client):
#     """
#     Main workflow to interact with the LLM remotely via SSH.

#     Steps:
#     - Check if Ollama CLI is installed on the remote host.
#     - List available models and allow user to select one.
#     - Ensure the selected model is available locally on the remote host.
#     - Offer user to run an interactive session or batch prompts from CSV.
#     """

#     try:
#         check_ollama_installed(ssh_client)
#     except Exception as e:
#         print(f"Error checking Ollama installation: {e}")
#         return

#     models = []
#     try:
#         models = get_available_models(ssh_client)
#     except Exception as e:
#         print(f"Error retrieving models: {e}")

#     if not models:
#         print("No available models found. Aborting.")
#         return

#     model = choose_model(models)
#     if model is None:
#         print("No model selected. Exiting.")
#         return

#     try:
#         ensure_model_available(ssh_client, model)
#     except Exception as e:
#         print(f"Error ensuring model availability: {e}")
#         return

#     print("\nLLM is ready to use. You can enter multiple prompts or CSV files.")
#     print("Type 'exit' anytime to quit.\n")

#     while True:
#         print("\nSelect input mode:")
#         print("1. Interactive session")
#         print("2. CSV file with prompts")
#         print("3. Exit")
#         mode = input("Enter choice (1, 2, or 3): ").strip()

#         if mode == "3" or mode.lower() == "exit":
#             print("Exiting workflow.")
#             break

#         if mode == "1":
#             try:
#                 interactive_session(ssh_client, model)
#             except Exception as e:
#                 print(f"Error during interactive session: {e}")

#         elif mode == "2":
#             try:
#                 cont = run_prompts_from_csv(ssh_client, model)
#                 if cont is False:
#                     print("Exiting workflow.")
#                     break
#             except Exception as e:
#                 print(f"Error running batch prompts: {e}")

#         else:
#             print("Invalid option. Please try again.")
