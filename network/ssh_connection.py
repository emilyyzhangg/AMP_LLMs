"""
SSH connection management with keepalive support.
"""
import asyncssh
import asyncio
from colorama import Fore
from config import get_config

config = get_config()


async def connect_ssh(ip, username, password):
    """
    Attempt SSH connection with keepalive configuration.
    """
    try:
        conn = await asyncssh.connect(
            host=ip,
            username=username,
            password=password,
            keepalive_interval=15,  # Send SSH keepalive every 15 seconds (INCREASED)
            keepalive_count_max=3,   # Allow 3 failures = 45 seconds (ADJUSTED)
            known_hosts=None,
            # ADD THESE TCP KEEPALIVE OPTIONS:
            tcp_keepalive=True,          # Enable TCP keepalive
            client_keys=None,            # Don't try key auth first
            connect_timeout=30,          # Connection timeout
        )
        return conn
    except asyncssh.PermissionDenied:
        print(Fore.RED + "Authentication failed.")
        return None
    except Exception as e:
        print(Fore.RED + f"SSH connection error: {e}")
        return None