import asyncio, shlex, re
from colorama import Fore

ANSI = re.compile(r'(?:\x1B[@-_][0-?]*[ -/]*[@-~])')

async def get_remote_models(session):
    try:
        stdin, stdout, stderr = await session.conn.open_session(asyncssh=True) if False else None
    except Exception:
        # fallback: run 'ollama list' over ssh via a helper command
        try:
            chan = session.conn.create_process('ollama list')
        except Exception:
            pass
    # Simplified: use exec_command via asyncssh connection
    try:
        result = await session.conn.run('ollama list', check=False)
        out = result.stdout or result.stderr or ''
        lines = [l.strip() for l in out.splitlines() if l.strip() and not l.lower().startswith('name')]
        models = [l.split()[0] for l in lines]
        return models
    except Exception as e:
        print(Fore.RED + f'Failed to list remote models: {e}')
        return []

async def run_remote_model_stream(session, model):
    print(Fore.MAGENTA + f\"\\n🌟 Starting interactive LLM session with {model}\")
    print(Fore.CYAN + \"(type 'main menu' or 'exit' to quit)\\n\")
    try:
        proc = await session.conn.create_process(f'ollama run {shlex.quote(model)}', stdin=asyncssh.PIPE, stdout=asyncssh.PIPE, stderr=asyncssh.PIPE)
    except Exception as e:
        print(Fore.RED + f'Failed to launch remote model: {e}'); return
    # streaming loop (simple)
    while True:
        prompt = input('>>> ').strip()
        if prompt.lower() in ('exit','quit'): break
        if prompt.lower() in ('main menu','menu','back'): break
        if not prompt: continue
        # send and stream output
        proc.stdin.write(prompt + '\\n')
        await proc.stdin.drain()
        # read until no more data for short period
        chunks = []
        try:
            while True:
                data = await asyncio.wait_for(proc.stdout.read(4096), timeout=0.5)
                if not data: break
                chunks.append(data.decode(errors='ignore'))
        except asyncio.TimeoutError:
            pass
        print('\\n' + ''.join(chunks))
