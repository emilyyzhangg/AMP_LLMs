import asyncssh, asyncio
from colorama import Fore

async def connect_ssh(ip, username, password):
    # Attempt connection once; return SSH client on success or None
    try:
        conn = await asyncssh.connect(host=ip, username=username, password=password)
        return conn
    except asyncssh.PermissionDenied:
        print(Fore.RED + "Authentication failed.")
        return None
    except Exception as e:
        print(Fore.RED + f"SSH connection error: {e}")
        return None
