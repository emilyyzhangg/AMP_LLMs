# network/networking.py
import platform, subprocess, shlex

def ping_host(host):
    system = platform.system().lower()
    if system == "windows":
        cmd = f"ping -n 1 {shlex.quote(host)}"
    else:
        cmd = f"ping -c 1 {shlex.quote(host)}"
    try:
        res = subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return res.returncode == 0
    except Exception:
        return False
