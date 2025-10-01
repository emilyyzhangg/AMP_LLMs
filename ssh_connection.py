import paramiko

def connect_ssh(hostname, port, username, password, timeout=10):
    """
    Establishes an SSH connection using paramiko.

    Args:
        hostname (str): SSH host/IP.
        port (int): SSH port.
        username (str): SSH username.
        password (str): SSH password.
        timeout (int, optional): Connection timeout in seconds. Defaults to 10.

    Returns:
        paramiko.SSHClient or None: Connected SSH client instance, or None on failure.
    """
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh_client.connect(
            hostname=hostname,
            port=port,
            username=username,
            password=password,
            timeout=timeout,
        )
        print(f"SSH connection established to {hostname}:{port} as {username}.\n")
        return ssh_client
    except paramiko.AuthenticationException:
        print("Authentication failed. Please check your username and password.")
    except paramiko.SSHException as ssh_exc:
        print(f"SSH error occurred: {ssh_exc}")
    except Exception as e:
        print(f"SSH connection failed: {e}")

    return None
