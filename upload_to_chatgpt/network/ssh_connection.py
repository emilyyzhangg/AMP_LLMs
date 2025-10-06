import paramiko
from colorama import Fore

def connect_ssh(ip, username, password):
    """Attempt SSH connection once using given credentials."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        print(Fore.YELLOW + f"🔐 Connecting to {username}@{ip} ...")
        ssh.connect(ip, username=username, password=password, port=22, timeout=10)
        return ssh

    except paramiko.AuthenticationException:
        print(Fore.RED + "❌ Authentication failed.")
        return None

    except paramiko.SSHException as e:
        print(Fore.RED + f"⚠️ SSH error: {e}")
        return None

    except KeyboardInterrupt:
        print(Fore.MAGENTA + "\n🚪 Connection cancelled by user.")
        return None

    except Exception as e:
        print(Fore.RED + f"❌ Unexpected error: {e}")
        return None
