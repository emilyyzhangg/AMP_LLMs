import pandas as pd
import shlex
from concurrent.futures import ThreadPoolExecutor, as_completed
from output_handler import save_responses_to_excel, save_responses_to_csv

def run_prompts_from_csv(ssh_client, model):
    while True:
        file_path = input("Enter CSV file path (or type 'exit' to quit): ").strip()
        if file_path.lower() == "exit":
            return False

        try:
            df = pd.read_csv(file_path)
        except Exception as e:
            print(f"Failed to read CSV: {e}")
            continue

        if 'Prompt' not in df.columns:
            print("CSV must contain a 'Prompt' column.")
            continue

        prompts = df['Prompt'].tolist()
        responses = []

        def run_prompt(p):
            safe_p = shlex.quote(p)
            ch = ssh_client.get_transport().open_session()
            ch.exec_command(f'zsh -l -c "ollama run {model} {safe_p}"')
            response = read_all_from_channel(ch)
            ch.close()
            return (p, response)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(run_prompt, p) for p in prompts]
            for future in as_completed(futures):
                responses.append(future.result())

        print(f"\nCompleted running {len(prompts)} prompts.")

        save_format = None
        while save_format not in ('csv', 'xlsx', 'exit'):
            save_format = input("Save results as (csv/xlsx) or 'exit' to skip saving: ").strip().lower()

        if save_format == 'csv':
            output_path = input("Enter CSV file path to save results: ").strip()
            save_responses_to_csv(responses, output_path)
        elif save_format == 'xlsx':
            output_path = input("Enter Excel file path to save results: ").strip()
            save_responses_to_excel(responses, output_path)
        else:
            print("Results not saved.")

        return True
