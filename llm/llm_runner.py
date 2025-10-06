# llm/llm_runner.py
from data.data_fetchers import fetch_clinical_trial_and_pubmed_pmc
from llm.interactive import interactive_session
from llm.llm_utils import list_local_models

def run_llm_entrypoint(ssh_client=None):
    models = list_local_models()
    if not models:
        print("No models found on local machine (ollama). You can still use remote via SSH.")
    model = None
    if models:
        print("Available models:")
        for i, m in enumerate(models, start=1):
            print(f" {i}) {m}")
        sel = input("Select model by number or name (leave blank to skip): ").strip()
        if sel:
            try:
                idx = int(sel)-1
                model = models[idx]
            except Exception:
                model = sel if sel in models else sel
    print("\\n1) Interactive session\\n2) Exit")
    choice = input("Select mode: ").strip()
    if choice == '1':
        interactive_session(ssh_client=ssh_client, model_name=model)
    else:
        print("Exiting.")

def main_connect_then_run(ssh_client=None):
    run_llm_entrypoint(ssh_client)
