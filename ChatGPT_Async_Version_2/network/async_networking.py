import asyncio
import platform
async def ping_host(host, timeout=1):
    # simple ping using system ping
    plat = platform.system().lower()
    if plat.startswith('win'):
        cmd = f'ping -n 1 -w {int(timeout*1000)} {host}'
    else:
        cmd = f'ping -c 1 -W {int(timeout)} {host}'
    proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    try:
        await asyncio.wait_for(proc.communicate(), timeout=timeout+1)
    except asyncio.TimeoutError:
        return False
    return proc.returncode == 0
