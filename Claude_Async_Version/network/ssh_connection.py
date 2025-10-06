import asyncssh, asyncio
from colorama import Fore

async def connect_ssh(ip, username, password):
    try:
        conn = await asyncssh.connect(
            host=ip, 
            username=username, 
            password=password,
            keepalive_interval=30,  # Send keepalive every 30 seconds
            keepalive_count_max=3   # Disconnect after 3 failed keepalives
        )
        return conn
    except asyncssh.PermissionDenied:
        print(Fore.RED + "Authentication failed.")
        return None
    except Exception as e:
        print(Fore.RED + f"SSH connection error: {e}")
        return None
