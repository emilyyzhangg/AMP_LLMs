import subprocess
import platform
import socket

def ping_host(hostname, count=5, timeout=1000, verbose=True):
    """
    Ping a host to check reachability.

    Parameters:
    - hostname: str, hostname or IP to ping.
    - count: int, number of ping attempts.
    - timeout: int, timeout per ping in milliseconds.
    - verbose: bool, whether to print output.

    Returns:
    - True if ping successful, False otherwise.
    """
    if verbose:
        print(f"Pinging {hostname} {count} times with timeout={timeout}ms...")

    system = platform.system().lower()
    if system == "windows":
        cmd = ["ping", "-n", str(count), "-w", str(timeout), hostname]
    else:
        timeout_sec = str(int(timeout) // 1000)
        cmd = ["ping", "-c", str(count), "-W", timeout_sec, hostname]

    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            if verbose:
                print("Ping successful.\n")
            return True
        else:
            if verbose:
                print("Ping failed.\n")
            return False
    except Exception as e:
        if verbose:
            print(f"Error during ping: {e}")
        return False

def check_port_open(host, port, timeout=3):
    """
    Check if a specific TCP port is open on a host.

    Parameters:
    - host: str, hostname or IP.
    - port: int, port number.
    - timeout: int, seconds to wait for connection.

    Returns:
    - True if port is open, False otherwise.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False

def prompt_for_reachable_host(default_host=None, max_attempts=5, timeout=1000):
    """
    Prompt user for a reachable host, verifying by ping.

    Parameters:
    - default_host: str or None, a default host to prefill.
    - max_attempts: int, number of ping attempts.
    - timeout: int, ping timeout in milliseconds.

    Returns:
    - hostname string if reachable.
    - None if user aborts.
    """
    while True:
        if default_host:
            prompt = f"Enter SSH host (default: {default_host}): "
            hostname = input(prompt).strip() or default_host
        else:
            hostname = input("Enter SSH host (e.g., 100.99.162.98): ").strip()

        if ping_host(hostname, count=max_attempts, timeout=timeout):
            return hostname

        print("Could not reach host.")
        choice = input("Try another IP? (y/n): ").strip().lower()
        if choice != 'y':
            print("Aborting.")
            return None
