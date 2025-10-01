import shlex
import time

def check_ollama_installed(ssh_client):
    """
    Check if Ollama CLI is installed on the remote host.
    If not installed, runs the install script and waits 10 seconds.
    """
    check_cmd = 'zsh -l -c "which ollama"'
    stdin, stdout, stderr = ssh_client.exec_command(check_cmd)
    if not stdout.read().decode().strip():
        print("Ollama not found. Installing...")
        install_cmd = 'zsh -l -c "curl -fsSL https://ollama.com/install.sh | sh"'
        ssh_client.exec_command(install_cmd)
        print("Installation command sent. Waiting 10 seconds for installation to complete...")
        time.sleep(10)
    else:
        print("Ollama is already installed.")

def get_available_models(ssh_client):
    """
    Return a sorted list of available Ollama models on the remote host.
    """
    cmd = 'zsh -l -c "ollama list"'
    stdin, stdout, stderr = ssh_client.exec_command(cmd)
    output = stdout.read().decode()
    if not output.strip():
        print("No models available via `ollama list`. Are you using the latest Ollama?")
        return []
    # Skip header and extract first column (model names)
    models = [line.strip().split()[0] for line in output.strip().splitlines() 
              if line and not line.lower().startswith('name')]
    return sorted(models)

def ensure_model_available(ssh_client, model):
    """
    Check if the specified model is available remotely; if not, pull it.
    """
    print(f"\nChecking if model '{model}' is available on the remote server...")
    list_cmd = 'zsh -l -c "ollama list"'
    stdin, stdout, stderr = ssh_client.exec_command(list_cmd)
    available_models = stdout.read().decode()

    if model not in available_models:
        print(f"Model '{model}' not found. Pulling now...")
        pull_cmd = f'zsh -l -c "ollama pull {shlex.quote(model)}"'
        stdin, stdout, stderr = ssh_client.exec_command(pull_cmd)
        output = stdout.read().decode()
        error = stderr.read().decode()
        if error:
            print("Error pulling model:", error)
        else:
            print(output)
    else:
        print(f"Model '{model}' is already available.")

def choose_model(models):
    """
    Prompt user to choose a model from the list or exit.
    """
    print("\nAvailable LLM models:")
    for i, model in enumerate(models, 1):
        print(f"{i}. {model}")
    while True:
        choice = input("Enter model number (or 'exit' to quit): ").strip()
        if choice.lower() == 'exit':
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(models):
            return models[int(choice) - 1]
        print("Invalid choice. Try again.")

def read_all_from_channel(channel):
    """
    Read all output from a paramiko channel until it's done.
    Returns the output as a string.
    """
    import time
    output_chunks = []
    while True:
        if channel.recv_ready():
            data = channel.recv(4096)
            if not data:
                break
            output_chunks.append(data)
        elif channel.exit_status_ready():
            break
        else:
            time.sleep(0.1)
    return b"".join(output_chunks).decode().strip()
