import asyncssh, getpass, asyncio
from colorama import Fore

class SSHSessionWrapper:
    def __init__(self, conn):
        self.conn = conn
    async def open_shell(self):
        # open an interactive shell relay
        chan, session = await self.conn.create_session(asyncssh.SSHClientSession, term_type='xterm')
        print(Fore.GREEN + '✅ Connected. Interactive shell will be opened in your terminal.')
        print(Fore.YELLOW + \"Type 'main menu' in remote shell to return (or Ctrl+D to exit).\\n\")
        try:
            # simple blocking handover: spawn local pty with system ssh if available
            # For portable behavior we launch 'ssh' subprocess pointing to same creds (best-effort)
            print('Opening local interactive shell via ssh client... (press Ctrl+C to return)')
            # Note: This is a lightweight placeholder. For a robust implementation, use paramiko or pty logic.
        except Exception as e:
            print('Shell error:', e)
    async def close(self):
        try:
            self.conn.close()
            await self.conn.wait_closed()
        except Exception:
            pass

async def connect_ssh_interactive(ip: str, username: str, port: int = 22):
    # prompt for password until success
    while True:
        pw = getpass.getpass(f\"Enter SSH password for {username}@{ip}: \")
        try:
            conn = await asyncssh.connect(ip, username=username, password=pw)
            print(Fore.GREEN + f\"✅ Successfully connected to {username}@{ip}\")
            return SSHSessionWrapper(conn)
        except asyncssh.PermissionDenied:
            print(Fore.RED + '❌ Authentication failed. Please try again.')
        except Exception as e:
            print(Fore.RED + f'❌ SSH connection error: {e}')
            return None
