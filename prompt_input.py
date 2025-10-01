import getpass
import socket

DEFAULT_HOST = "100.99.162.98"
DEFAULT_PORT = 22

def prompt_for_connection():
    """
    Prompt user for SSH connection details with reachability check and basic validation.
    Returns:
        Tuple (host, port, username, password) or None if user aborts.
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

        # Check connectivity
        try:
            socket.create_connection((ip, port), timeout=5)
        except socket.error:
            print(f"Cannot reach {ip}:{port}. Try again.")
            continue

        # Username prompt with validation
        while True:
            username = input("Enter SSH username (or 'exit'): ").strip()
            if username.lower() == "exit":
                return None
            if username:
                break
            print("Username cannot be empty.")

        # Password prompt with validation
        while True:
            password = getpass.getpass(f"Password for {username}@{ip}:{port} (or type 'exit'): ")
            if password.lower() == "exit":
                return None
            if password:
                break
            print("Password cannot be empty.")

        # All inputs gathered successfully
        return ip, port, username, password
