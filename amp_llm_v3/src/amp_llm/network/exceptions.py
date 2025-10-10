"""Custom exceptions for network operations."""


class NetworkError(Exception):
    """Base exception for network operations."""
    pass


class SSHConnectionError(NetworkError):
    """SSH connection failed."""
    pass


class ShellDetectionError(NetworkError):
    """Failed to detect remote shell."""
    pass


class TunnelError(NetworkError):
    """Tunnel operation failed."""
    pass