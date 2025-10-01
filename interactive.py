from output_handler import save_responses_to_excel, save_responses_to_csv

def interactive_session(ssh_client, model):
    import shlex
    import time
    from output_handler import save_responses_to_excel

    print("\nStarting interactive LLM session (type 'exit' to quit)...\n")
    conversation = []

    channel = ssh_client.get_transport().open_session()
    channel.get_pty()  # Request a pseudo-terminal here!
    safe_model = shlex.quote(model)
    command = f'zsh -l -c "ollama run {safe_model}"'
    channel.exec_command(command)

    # Flush initial output
    time.sleep(0.5)
    while channel.recv_ready():
        _ = channel.recv(4096).decode()

    try:
        while True:
            prompt = input("Enter prompt: ").strip()
            if prompt.lower() == 'exit':
                print("Ending interactive session.")
                break
            if not prompt:
                continue  # skip empty inputs

            # Send prompt to LLM
            channel.send(prompt + "\n")

            response_chunks = []
            start_time = time.time()

            # Read until no data arrives for 3 seconds
            while True:
                if channel.recv_ready():
                    chunk = channel.recv(4096).decode()
                    response_chunks.append(chunk)
                    start_time = time.time()  # reset timer on data
                else:
                    if time.time() - start_time > 3:
                        break
                    time.sleep(0.1)

                if channel.exit_status_ready():
                    break

            response = "".join(response_chunks).strip()
            print(f"\nResponse:\n{response}\n")
            conversation.append((prompt, response))

    except KeyboardInterrupt:
        print("\nSession interrupted by user.")
    except Exception as e:
        print(f"Error during interactive session: {e}")
    finally:
        # Save conversation if any
        if conversation:
            save_format = None
            while save_format not in ('csv', 'xlsx', 'exit'):
                save_format = input("Save conversation as (csv/xlsx) or 'exit' to skip saving: ").strip().lower()

            if save_format == 'csv':
                path = input("Enter CSV file path to save conversation: ").strip()
                save_responses_to_excel(conversation, path, csv_mode=True)
            elif save_format == 'xlsx':
                path = input("Enter Excel file path to save conversation: ").strip()
                save_responses_to_excel(conversation, path, csv_mode=False)
            else:
                print("Conversation not saved.")

        if channel is not None:
            channel.close()
