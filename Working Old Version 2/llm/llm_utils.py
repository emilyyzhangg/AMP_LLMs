# llm_utils.py
import shlex
import time
import re
import subprocess


# === Remote Ollama ===
def check_ollama_installed(ssh_client):
    stdin, stdout, stderr = ssh_client.exec_command('zsh -l -c "which ollama"')
    path = stdout.read().decode().strip()
    if not path:
        raise EnvironmentError(
            "Ollama not found on remote. Install it with:\n"
            "/bin/bash -c \"$(curl -fsSL https://ollama.com/install.sh)\""
        )
    print(f"Ollama found: {path}")


def get_available_models(ssh_client):
    stdin, stdout, stderr = ssh_client.exec_command('zsh -l -c "ollama list"')
    output = stdout.read().decode()
    if not output.strip():
        print("No remote models found.")
        return []
    return sorted([
        line.strip().split()[0]
        for line in output.strip().splitlines()
        if line and not line.lower().startswith('name')
    ])


def ensure_model_available(ssh_client, model):
    models = get_available_models(ssh_client)
    if model not in models:
        print(f"Pulling model '{model}'...")
        cmd = f'zsh -l -c "ollama pull {shlex.quote(model)}"'
        stdin, stdout, stderr = ssh_client.exec_command(cmd)
        print(stdout.read().decode() or stderr.read().decode())
        time.sleep(5)


def run_ollama_remote(ssh_client, model, prompt):
    cmd = f'zsh -l -c "ollama run {shlex.quote(model)}"'
    stdin, stdout, stderr = ssh_client.exec_command(cmd)
    stdin.write(prompt + "\n")
    stdin.flush()
    stdin.channel.shutdown_write()
    return clean_ollama_output(stdout.read().decode() or stderr.read().decode())


# === Local Ollama ===
ANSI_ESCAPE = re.compile(r'(?:\x1B[@-_][0-?]*[ -/]*[@-~])')


def clean_ollama_output(text):
    return ANSI_ESCAPE.sub("", text).strip()


def run_ollama_local(model, prompt):
    cmd = f'zsh -l -c "ollama run {shlex.quote(model)}"'
    proc = subprocess.Popen(
        cmd, shell=True, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    stdout, stderr = proc.communicate(prompt + "\n")
    return clean_ollama_output(stdout or stderr)

def run_interactive_ollama_shell(ssh_client, model):
    import shlex
    import time
    from data.output_handler import save_responses_to_excel  # Adjust import path as needed

    print("\n🧠 Starting interactive Ollama shell session (type 'exit' to quit)...\n")
    conversation = []

    channel = ssh_client.get_transport().open_session()
    channel.get_pty()
    safe_model = shlex.quote(model)
    command = f'zsh -l -c "ollama run {safe_model}"'
    channel.exec_command(command)

    # Flush initial output
    time.sleep(0.5)
    while channel.recv_ready():
        _ = channel.recv(4096).decode()

    try:
        while True:
            prompt = input("You: ").strip()
            if prompt.lower() == 'exit':
                print("👋 Ending interactive session.")
                break
            if not prompt:
                continue

            channel.send(prompt + "\n")

            response_chunks = []
            start_time = time.time()

            while True:
                if channel.recv_ready():
                    chunk = channel.recv(4096).decode()
                    response_chunks.append(chunk)
                    start_time = time.time()
                else:
                    if time.time() - start_time > 3:
                        break
                    time.sleep(0.1)

                if channel.exit_status_ready():
                    break

            response = "".join(response_chunks).strip()
            print(f"\n🧠 Ollama:\n{response}\n")
            conversation.append((prompt, response))

    except KeyboardInterrupt:
        print("\n⛔ Session interrupted by user.")
    except Exception as e:
        print(f"❌ Error during interactive session: {e}")
    finally:
        if conversation:
            save_format = None
            while save_format not in ('csv', 'xlsx', 'exit'):
                save_format = input("Save conversation as (csv/xlsx) or 'exit' to skip saving: ").strip().lower()

            if save_format in ('csv', 'xlsx'):
                path = input("Enter filename to save conversation: ").strip()
                save_responses_to_excel(conversation, path, csv_mode=(save_format == 'csv'))
                print(f"✅ Saved to {path}")
            else:
                print("❌ Conversation not saved.")

        if channel is not None:
            channel.close()

def run_ollama_local_with_file(ollama_path, model, file_path):
    print(f"Running model '{model}' on file '{file_path}'...")
    if not os.path.isfile(file_path):
        print(f"File not found: {file_path}")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        prompt = f.read()

    output = run_ollama_local(model, prompt)
    print("\n=== LLM Output ===\n")
    print(output)
    print("==================\n")


def list_local_models(ollama_path="ollama"):
    try:
        result = subprocess.run([ollama_path, "list"], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            print(f"Ollama error: {result.stderr.strip()}")
            return []
        lines = result.stdout.strip().splitlines()
        return sorted([
            line.split()[0]
            for line in lines
            if line and not line.lower().startswith("name")
        ])
    except Exception as e:
        print(f"Model listing failed: {e}")
        return []


# === User Prompt Helper ===
def choose_model(models):
    print("\nAvailable LLM models:")
    for i, model in enumerate(models, 1):
        print(f"{i}. {model}")

    while True:
        choice = input("Enter model number (or 'exit' or 'main menu' to go back): ").strip().lower()
        if choice == 'exit':
            return None
        if choice == 'main menu':
            return "main_menu"
        if choice.isdigit() and 1 <= int(choice) <= len(models):
            return models[int(choice) - 1]
        print("Invalid choice. Try again.")
