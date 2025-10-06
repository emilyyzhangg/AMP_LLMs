import asyncio, shlex, re
ANSI_ESCAPE = re.compile(r'(?:\x1B[@-_][0-?]*[ -/]*[@-~])')
def clean(text):
    return ANSI_ESCAPE.sub('', text).strip()

async def list_remote_models(ssh):
    try:
        result = await ssh.run('ollama list', check=False)
        out = result.stdout or result.stderr
        if not out or 'NAME' not in out:
            return []
        models = []
        for line in out.splitlines():
            if not line.strip() or line.lower().startswith('name'): continue
            parts = line.split()
            models.append(parts[0])
        return models
    except Exception:
        return []

async def start_persistent_ollama(ssh, model):
    """Start persistent ollama run process and return process handle object with stdin/stdout methods.""\    # uses ssh.create_process to get stdin/out as streams
    proc = await ssh.create_process(f'ollama run {shlex.quote(model)}', term_type='xterm')
    return proc

async def send_and_stream(proc, prompt, timeout=10):
    # write prompt then read streamed output until idle timeout
    try:
        proc.stdin.write(prompt + "\n")
        await proc.stdin.drain()
    except Exception:
        pass
    output = []
    idle = 0
    while True:
        try:
            chunk = await asyncio.wait_for(proc.stdout.read(1024), timeout=1.0)
        except asyncio.TimeoutError:
            idle += 1
            if idle > 3:
                break
            else:
                continue
        if not chunk:
            break
        output.append(chunk)
        idle = 0
    return clean(''.join(output))
