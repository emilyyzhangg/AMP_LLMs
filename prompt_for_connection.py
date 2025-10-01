import getpass
import socket
import subprocess
import platform

DEFAULT_HOST = "100.99.162.98"
DEFAULT_PORT = 22

def is_host_reachable(host, port, timeout=5):
    """
    Check if the host and port are reachable using TCP socket connection.
    Falls back to ping command if socket connect fails.
    
    Returns:
        True if reachable, False otherwise.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        # Fallback to ping as secondary reachability test
        try:
            if platform.system().lower().startswith("win"):
                cmd = ["ping", "-n", "1", host]
            else:
                cmd = ["ping", "-c", "1", host]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return res.returncode == 0
        except Exception:
            return False

def prompt_for_connection():
    """
    Prompt user for SSH connection details with validation and reachability checks.
    Returns:
        Tuple (host, port, username, password) or None if user exits.
    """
    while True:
        ip_input = input(f"Enter SSH host (default: {DEFAULT_HOST}, or type 'exit' to quit): ").strip()
        if ip_input.lower() == "exit":
            return None
        ip = ip_input or DEFAULT_HOST

        port_input = input(f"Enter SSH port (default: {DEFAULT_PORT}, or 'exit'): ").strip()
        if port_input.lower() == "exit":
            return None
        if port_input == "":
            port = DEFAULT_PORT
        elif port_input.isdigit() and 1 <= int(port_input) <= 65535:
            port = int(port_input)
        else:
            print("Invalid port. Please enter a number between 1 and 65535 or leave blank for default.")
            continue

        print(f"Checking reachability of {ip}:{port}...")
        if not is_host_reachable(ip, port):
            print(f"Cannot reach {ip}:{port}.")
            retry = input("Try entering host/port again? (y/n): ").strip().lower()
            if retry != 'y':
                return None
            else:
                continue

        username = input("Enter SSH username (or 'exit'): ").strip()
        if username.lower() == "exit":
            return None
        if not username:
            print("Username cannot be empty.")
            continue

        password = getpass.getpass(f"Password for {username}@{ip}:{port}: ")
        if password.lower() == "exit":
            return None
        if not password:
            print("Password cannot be empty.")
            continue

        # All inputs valid and reachable
        return ip, port, username, password
