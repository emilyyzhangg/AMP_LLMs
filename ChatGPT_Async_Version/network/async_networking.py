import asyncio, platform, subprocess
async def ping_host(ip: str, timeout: int = 2) -> bool:
    # simple cross-platform ping wrapper
    proc = None
    system = platform.system().lower()
    if system.startswith('win'):
        cmd = ['ping', '-n', '1', '-w', str(timeout*1000), ip]
    else:
        cmd = ['ping', '-c', '1', '-W', str(timeout), ip]
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await asyncio.wait_for(proc.communicate(), timeout=timeout+1)
        return proc.returncode == 0
    except Exception:
        return False
