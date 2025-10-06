import subprocess
import shlex
import time
import re
import os


# === Utility: Clean up output ===
ANSI_ESCAPE = re.compile(r'(?:\x1B[@-_][0-?]*[ -/]*[@-~])')


def clean_ollama_output(text):
    """Remove ANSI escape sequences for clean output."""
    return ANSI_ESCAPE.sub("", text).strip()


# === Remote Ollama ===
def check_ollama_installed(ssh_client):
    """Check if Ollama is installed on the remote host."""
    stdin, stdout, stderr = ssh_client.exec_command('zsh -i -l -c "which ollama"')
    path = stdout.read().decode().strip()
    if not path:
        raise EnvironmentError(
            "❌ Ollama not found on remote. Install it with:\n"
            '/bin/bash -c "$(curl -fsSL https://ollama.com/install.sh)"'
        )
    print(f"✅ Ollama found at: {path}")


def get_available_models(ssh_client):
    """
    Retrieve all available Ollama models on the remote machine.
    Uses zsh interactive login to ensure environment variables load properly.
    """
    stdin, stdout, stderr = ssh_client.exec_command('zsh -i -l -c "ollama list"')
    output = stdout.read().decode(errors="ignore").strip()
    err = stderr.read().decode(errors="ignore").strip()

    if not output and err:
        print(f"⚠️ Ollama error: {err}")
        return []

    if not output:
        print("⚠️ No remote models found.")
        return []

    models = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("name"):
            continue
        parts = line.split()
        if len(parts) >= 1:
            models.append(parts[0])

    return sorted(models)


def ensure_model_available(ssh_client, model):
    """Ensure the specified model exists remotely, or pull it if missing."""
    models = get_available_models(ssh_client)
    if model not in models:
        print(f"⬇️ Pulling model '{model}' from Ollama registry...")
        cmd = f'zsh -i -l -c "ollama pull {shlex.quote(model)}"'
        stdin, stdout, stderr = ssh_client.exec_command(cmd)
        output = stdout.read().decode() or stderr.read().decode()
        print(clean_ollama_output(output))
        time.sleep(5)


def run_ollama_remote(ssh_client, model, prompt):
    """Run a prompt on a remote Ollama model and return its output."""
    cmd = f'zsh -i -l -c "ollama run {shlex.quote(model)}"'
    stdin, stdout, stderr = ssh_client.exec_command(cmd)
    stdin.write(prompt + "\n")
    stdin.flush()
    stdin.channel.shutdown_write()

    out = stdout.read().decode(errors="ignore")
    err = stderr.read().decode(errors="ignore")
    return clean_ollama_output(out or err)


def run_interactive_ollama_shell(ssh_client, model):
    """Start an interactive Ollama chat session on the remote host."""
    from data.output_handler import save_responses_to_excel

    print("\n🧠 Starting interactive Ollama shell (type 'exit' to quit)...\n")
    conversation = []

    channel = ssh_client.get_transport().open_session()
    channel.get_pty()
    command = f'zsh -i -l -c "ollama run {shlex.quote(model)}"'
    channel.exec_command(command)

    time.sleep(0.5)
    while channel.recv_ready():
        _ = channel.recv(4096).decode()

    try:
        while True:
            prompt = input("You: ").strip()
            if prompt.lower() == "exit":
                print("👋 Ending interactive session.")
                break
            if not prompt:
                continue

            channel.send(prompt + "\n")

            response_chunks = []
            start_time = time.time()

            while True:
                if channel.recv_ready():
                    chunk = channel.recv(4096).decode(errors="ignore")
                    response_chunks.append(chunk)
                    start_time = time.time()
                else:
                    if time.time() - start_time > 3:
                        break
                    time.sleep(0.1)

                if channel.exit_status_ready():
                    break

            response = clean_ollama_output("".join(response_chunks))
            print(f"\n🧠 Ollama:\n{response}\n")
            conversation.append((prompt, response))

    except KeyboardInterrupt:
        print("\n⛔ Session interrupted by user.")
    except Exception as e:
        print(f"❌ Error during interactive session: {e}")
    finally:
        if conversation:
            save_format = None
            while save_format not in ("csv", "xlsx", "exit"):
                save_format = input("Save conversation as (csv/xlsx) or 'exit' to skip saving: ").strip().lower()

            if save_format in ("csv", "xlsx"):
                path = input("Enter filename to save conversation: ").strip()
                save_responses_to_excel(conversation, path, csv_mode=(save_format == "csv"))
                print(f"✅ Saved conversation to {path}")
            else:
                print("❌ Conversation not saved.")

        channel.close()


# === Local Ollama ===
def run_ollama_local(model, prompt):
    """Run a local Ollama model."""
    cmd = f'zsh -i -l -c "ollama run {shlex.quote(model)}"'
    proc = subprocess.Popen(
        cmd, shell=True, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    stdout, stderr = proc.communicate(prompt + "\n")
    return clean_ollama_output(stdout or stderr)


def run_ollama_local_with_file(model, file_path):
    """Run a model locally using prompts from a file."""
    print(f"📄 Running model '{model}' on file '{file_path}'...")
    if not os.path.isfile(file_path):
        print(f"❌ File not found: {file_path}")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        prompt = f.read()

    output = run_ollama_local(model, prompt)
    print("\n=== LLM Output ===\n")
    print(output)
    print("==================\n")


def list_local_models():
    """List all locally available Ollama models."""
    try:
        result = subprocess.run(
            ["zsh", "-i", "-l", "-c", "ollama list"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            print(f"⚠️ Ollama error: {result.stderr.strip()}")
            return []

        lines = result.stdout.strip().splitlines()
        models = []
        for line in lines:
            line = line.strip()
            if not line or line.lower().startswith("name"):
                continue
            parts = line.split()
            if len(parts) >= 1:
                models.append(parts[0])

        return sorted(models)
    except Exception as e:
        print(f"❌ Model listing failed: {e}")
        return []


# === Model Selection Helper ===
def choose_model(models):
    """Prompt user to pick a model from a list."""
    print("\nAvailable LLM models:")
    for i, model in enumerate(models, 1):
        print(f"{i}. {model}")

    while True:
        choice = input("Enter model number (or 'exit' or 'main menu' to go back): ").strip().lower()
        if choice == "exit":
            return None
        if choice == "main menu":
            return "main_menu"
        if choice.isdigit() and 1 <= int(choice) <= len(models):
            return models[int(choice) - 1]
        print("Invalid choice. Try again.")
