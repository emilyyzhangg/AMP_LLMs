import csv
import shlex
from llm_utils import clean_ollama_output


def run_batch(csv_file, model_name, ssh_client=None):
    """
    Run batch prompts from a CSV file using Ollama over SSH.
    The CSV must have a column named 'prompt'.
    """
    if ssh_client is None:
        raise ValueError("SSH client required for remote Ollama execution.")

    safe_model = shlex.quote(model_name)

    with open(csv_file, newline='', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        if 'prompt' not in reader.fieldnames:
            raise ValueError("CSV file must contain a 'prompt' column.")

        results = []
        for row in reader:
            prompt = row['prompt']
            print(f"\n[INFO] Running prompt: {prompt[:60]}...")

            command = f'zsh -l -c "ollama run {safe_model}"'
            stdin, stdout, stderr = ssh_client.exec_command(command)
            stdin.write(prompt + "\n")
            stdin.flush()
            stdin.channel.shutdown_write()

            output = stdout.read().decode() or stderr.read().decode()
            cleaned = clean_ollama_output(output)

            results.append({
                "prompt": prompt,
                "response": cleaned
            })

            print("[RESPONSE]", cleaned[:200], "...\n")

    return results


def run_prompts_from_csv(ssh_client, model_name):
    """
    Prompt user for CSV path, run all prompts, and save results.
    Returns False if user cancels.
    """
    csv_file = input("Enter path to CSV file with prompts (or 'exit' to cancel): ").strip()
    if not csv_file or csv_file.lower() == 'exit':
        return False

    try:
        results = run_batch(csv_file, model_name, ssh_client=ssh_client)
    except Exception as e:
        print(f"Error running prompts from CSV: {e}")
        return False

    print(f"[INFO] Completed {len(results)} prompts from {csv_file}")
    # (Optional) Save results to new CSV
    out_file = csv_file.replace(".csv", "_results.csv")
    with open(out_file, "w", newline='', encoding="utf-8") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=["prompt", "response"])
        writer.writeheader()
        writer.writerows(results)
    print(f"[INFO] Results saved to {out_file}")

    return True
