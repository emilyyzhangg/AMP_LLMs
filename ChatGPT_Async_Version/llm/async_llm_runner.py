import asyncio
from colorama import Fore
from .async_llm_utils import get_remote_models, run_remote_model_stream

async def run_llm_entrypoint_async(session):
    print(Fore.CYAN + '\\n=== ⚙️ LLM Workflow ===')
    models = await get_remote_models(session)
    if not models:
        print(Fore.RED + '⚠️ No Ollama models found remotely.')
        return
    for i,m in enumerate(models,1):
        print(f' {i}) {m}')
    choice = input(Fore.GREEN + 'Select model by number or name (leave blank to skip): ').strip()
    if not choice or choice.lower() in ('main menu','menu','back'):
        print(Fore.YELLOW + '↩ Returning to main menu...')
        return
    selected = None
    if choice.isdigit() and 1 <= int(choice) <= len(models):
        selected = models[int(choice)-1]
    else:
        for m in models:
            if m.lower() == choice.lower():
                selected = m; break
    if not selected:
        print(Fore.RED + '⚠️ Invalid model selection.')
        return
    print(Fore.YELLOW + f\"\\n✨ Selected model: {selected}\")
    await run_remote_model_stream(session, selected)
