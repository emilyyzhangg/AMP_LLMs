from colorama import Fore
from .async_llm_utils import list_remote_models, start_persistent_ollama, send_and_stream
import asyncio

async def run_llm_entrypoint(ssh):
    print(Fore.CYAN + "=== ⚙️ LLM Workflow ===")
    models = await list_remote_models(ssh)
    if not models:
        print(Fore.RED + "⚠️ No Ollama models found on remote.")
        return
    for i,m in enumerate(models,1):
        print(f" {i}) {m}")
    choice = input(Fore.GREEN + "Select model by number or name (blank to cancel): " )
    if not choice.strip():
        print("Cancelled.")
        return
    model = None
    if choice.isdigit():
        idx = int(choice)-1
        if 0 <= idx < len(models): model = models[idx]
    else:
        for m in models:
            if m.lower()==choice.lower(): model=m; break
    if not model:
        print(Fore.RED + "Invalid model."); return
    print(Fore.YELLOW + f"Starting model: {model}")
    proc = await start_persistent_ollama(ssh, model)
    try:
        while True:
            prompt = input('>>> ').strip()
            if prompt.lower() in ('exit','quit'):
                break
            if prompt.lower() in ('main menu','menu'):
                break
            if not prompt: continue
            out = await send_and_stream(proc, prompt)
            print('\n🧠 Model output:\n', out)
    finally:
        try:
            proc.stdin.close()
            proc.stdout.close()
            proc.close()
        except Exception:
            pass
