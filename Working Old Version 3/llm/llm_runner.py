import time
from colorama import Fore

def list_ollama_models(ssh):
    """List remote Ollama models via SSH with proper environment sourcing."""
    try:
        # Use interactive login shell to ensure PATH & env are loaded
        stdin, stdout, stderr = ssh.exec_command('zsh -i -l -c "ollama list"')
        output = stdout.read().decode(errors="ignore").strip()
        err = stderr.read().decode(errors="ignore").strip()

        if not output and err:
            print(Fore.RED + f"⚠️ Ollama error: {err}")
            return []

        if not output or "NAME" not in output:
            print(Fore.RED + "⚠️ No Ollama models found.")
            return []

        lines = [l.strip() for l in output.splitlines() if l.strip()]
        models = []
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 4:
                models.append({
                    "name": parts[0],
                    "model_id": parts[1],
                    "size": parts[2],
                    "age": " ".join(parts[3:])
                })
        return models

    except Exception as e:
        print(Fore.RED + f"❌ Failed to list models: {e}")
        return []



def run_llm_entrypoint(ssh):
    """Remote Ollama model selection and workflow."""
    print(Fore.CYAN + "Available models:")
    models = list_ollama_models(ssh)
    if not models:
        print(Fore.RED + "❌ No models available. Ensure Ollama is installed and models are pulled.")
        return

    for idx, m in enumerate(models, 1):
        print(f" {idx}) {m['name']:20s} {m['model_id']:15s} {m['size']:>6s} {m['age']}")

    choice = input(Fore.GREEN + "Select model by number or name (leave blank to skip): ").strip()
    if not choice or choice.lower() in ["main menu", "menu", "back"]:
        print(Fore.YELLOW + "↩ Returning to main menu...")
        return

    selected = None
    if choice.isdigit() and 1 <= int(choice) <= len(models):
        selected = models[int(choice) - 1]["name"]
    else:
        for m in models:
            if m["name"].lower() == choice.lower():
                selected = m["name"]
                break

    if not selected:
        print(Fore.RED + "⚠️ Invalid model choice. Returning to main menu.")
        return

    print(Fore.YELLOW + f"\n✨ Selected model: {selected}")
    run_interactive_llm(selected, ssh)


def run_interactive_llm(model_name, ssh):
    """
    Maintain a persistent interactive session with Ollama remotely.
    Streams output live, preserves context, and suppresses prompt echo.
    """
    import time
    import threading
    from colorama import Fore

    print(Fore.MAGENTA + f"\n🌟 Starting interactive LLM session with {model_name}")
    print(Fore.CYAN + "(type 'main menu' or 'exit' to quit)\n")

    # Create SSH channel and launch ollama interactively
    channel = ssh.get_transport().open_session()
    channel.get_pty()
    channel.exec_command(f'zsh -i -l -c "ollama run {model_name}"')

    # Keep track of last sent prompt to filter echo
    last_prompt = {"text": ""}

    # --- Reader thread: stream output without echoing back user input ---
    def reader():
        try:
            while True:
                if channel.recv_ready():
                    chunk = channel.recv(4096).decode(errors="ignore")
                    if not chunk:
                        break

                    # Skip redundant echo lines (user's last prompt)
                    if last_prompt["text"] and last_prompt["text"] in chunk:
                        chunk = chunk.replace(last_prompt["text"], "")

                    print(chunk, end="", flush=True)
                elif channel.exit_status_ready():
                    break
                else:
                    time.sleep(0.05)
        except Exception as e:
            print(Fore.RED + f"\n[Stream error: {e}]")

    reader_thread = threading.Thread(target=reader, daemon=True)
    reader_thread.start()

    # --- Input loop ---
    try:
        while True:
            user_input = input(Fore.WHITE + ">>> " + Fore.RESET).strip()
            if not user_input:
                continue

            # Exit commands
            if user_input.lower() in ["exit", "quit", "/bye"]:
                channel.send("/bye\n")
                print(Fore.MAGENTA + "👋 Ending LLM session.\n")
                break
            elif user_input.lower() in ["main menu", "menu", "back"]:
                print(Fore.YELLOW + "↩ Returning to main menu...\n")
                break

            # Remember last prompt for echo suppression
            last_prompt["text"] = user_input.strip()

            # Send message to remote model
            channel.send(user_input + "\n")

    except KeyboardInterrupt:
        print(Fore.MAGENTA + "\n⛔ Interrupted by user.")
    finally:
        try:
            channel.close()
        except Exception:
            pass
