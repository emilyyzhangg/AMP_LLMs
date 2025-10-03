# llm_utils.py
import shlex
import time
import re

def check_ollama_installed(ssh_client):
    """
    Check if Ollama CLI is installed on the remote host.
    """
    stdin, stdout, stderr = ssh_client.exec_command('zsh -l -c "which ollama"')
    path = stdout.read().decode().strip()
    if not path:
        raise EnvironmentError(
            "Ollama is not installed on the remote host. Please install it:\n"
            "  /bin/bash -c \"$(curl -fsSL https://ollama.com/install.sh)\""
        )
    print(f"Ollama found at: {path}")


def get_available_models(ssh_client):
    """
    Return a sorted list of available Ollama models on the remote host.
    """
    stdin, stdout, stderr = ssh_client.exec_command('zsh -l -c "ollama list"')
    output = stdout.read().decode()
    if not output.strip():
        print("No models available via `ollama list`. You may need to pull a model.")
        return []
    # Skip header and extract first column (model names)
    models = [line.strip().split()[0] for line in output.strip().splitlines()
              if line and not line.lower().startswith('name')]
    return sorted(models)


def ensure_model_available(ssh_client, model):
    """
    Check if the specified model is available; if not, pull it.
    """
    models = get_available_models(ssh_client)
    if model not in models:
        print(f"Model '{model}' not found. Pulling now...")
        pull_cmd = f'zsh -l -c "ollama pull {shlex.quote(model)}"'
        stdin, stdout, stderr = ssh_client.exec_command(pull_cmd)
        stdout_text = stdout.read().decode()
        stderr_text = stderr.read().decode()
        if stderr_text:
            print(f"Error pulling model: {stderr_text}")
        else:
            print(stdout_text)
        time.sleep(5)
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


def clean_ollama_output(text):
    """
    Clean Ollama output (strip extra whitespace, artifacts).
    """
    return text.strip()


def query_ollama(model, prompt):
    """
    Run Ollama locally (subprocess) and clean output.
    """
    import subprocess

    ANSI_ESCAPE = re.compile(r'(?:\x1B[@-_][0-?]*[ -/]*[@-~])')

    def clean(text):
        return ANSI_ESCAPE.sub("", text).strip()

    import shlex
    safe_model = shlex.quote(model)
    cmd = f'zsh -l -c "ollama run {safe_model}"'
    process = subprocess.Popen(
        cmd, shell=True, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    stdout, stderr = process.communicate(prompt + "\n")
    output = stdout or stderr
    return clean(output)


def run_ollama(ssh_client, model, prompt):
    """
    Universal Ollama runner — ensures consistent execution inside a login shell.
    """
    safe_model = shlex.quote(model)
    cmd = f'zsh -l -c "ollama run {safe_model}"'

    stdin, stdout, stderr = ssh_client.exec_command(cmd)
    stdin.write(prompt + "\n")
    stdin.flush()
    stdin.channel.shutdown_write()

    output = stdout.read().decode() or stderr.read().decode()
    return clean_ollama_output(output)
