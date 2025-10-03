import subprocess
import platform
import socket

def ping_host(host, count=3, timeout=1000):
    """
    Pings a host to check connectivity.

    Args:
        host (str): The hostname or IP address to ping.
        count (int): Number of ping attempts.
        timeout (int): Timeout per ping in milliseconds.

    Returns:
        bool: True if ping succeeds, False otherwise.
    """
    system = platform.system().lower()

    if system == 'windows':
        cmd = ['ping', '-n', str(count), '-w', str(timeout), host]
    else:
        # Unix/Linux/Mac: timeout in seconds
        timeout_sec = str(int(timeout / 1000))
        cmd = ['ping', '-c', str(count), '-W', timeout_sec, host]

    try:
        subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError:
        return False

def check_port_open(host, port, timeout=5):
    """
    Checks if a TCP port is open on a given host.

    Args:
        host (str): Hostname or IP address.
        port (int): Port number to check.
        timeout (int, optional): Timeout in seconds. Default is 5.

    Returns:
        bool: True if port is open, False otherwise.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False
