# network/ssh_connection.py
import paramiko, getpass, socket

def connect_ssh(host, username, port=22, timeout=10):
    password = getpass.getpass(f"Password for {username}@{host}: ")
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=host, port=port, username=username, password=password, timeout=timeout)
        print("✅ SSH connection established.")
        return client
    except paramiko.AuthenticationException:
        print("❌ Authentication failed.")
    except socket.timeout:
        print("❌ Connection timed out.")
    except Exception as e:
        print("❌ SSH connection error:", e)
    return None
