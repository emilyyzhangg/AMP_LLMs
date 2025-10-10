"""
Output management utilities.
"""

import sys
from typing import Optional, TextIO
from pathlib import Path
from datetime import datetime, timedelta
from colorama import Fore, Style


# =============================================================================
# Output Destinations
# =============================================================================

class OutputManager:
    """
    Manages output to multiple destinations.
    
    Example:
        >>> output = OutputManager()
        >>> output.add_destination(ConsoleOutput())
        >>> output.add_destination(FileOutput("log.txt"))
        >>> output.write("Hello World")
    """
    
    def __init__(self):
        self.destinations = []
    
    def add_destination(self, destination):
        """Add output destination."""
        self.destinations.append(destination)
    
    def write(self, text: str):
        """Write to all destinations."""
        for dest in self.destinations:
            dest.write(text)
    
    def writeln(self, text: str = ""):
        """Write line to all destinations."""
        self.write(text + "\n")
    
    def flush(self):
        """Flush all destinations."""
        for dest in self.destinations:
            dest.flush()
    
    def close(self):
        """Close all destinations."""
        for dest in self.destinations:
            dest.close()


class ConsoleOutput:
    """Output to console/stdout."""
    
    def __init__(self, stream: TextIO = sys.stdout):
        self.stream = stream
    
    def write(self, text: str):
        """Write to console."""
        self.stream.write(text)
    
    def flush(self):
        """Flush stream."""
        self.stream.flush()
    
    def close(self):
        """No-op for console."""
        pass


class FileOutput:
    """Output to file."""
    
    def __init__(self, path: Path, mode: str = 'a'):
        self.path = Path(path)
        self.mode = mode
        self.file: Optional[TextIO] = None
        self._open()
    
    def _open(self):
        """Open file."""
        self.path.parent.mkdir(exist_ok=True, parents=True)
        self.file = open(self.path, self.mode, encoding='utf-8')
    
    def write(self, text: str):
        """Write to file."""
        if self.file:
            # Strip color codes for file output
            import re
            text = re.sub(r'\x1b\[[0-9;]*m', '', text)
            self.file.write(text)
    
    def flush(self):
        """Flush file."""
        if self.file:
            self.file.flush()
    
    def close(self):
        """Close file."""
        if self.file:
            self.file.close()
            self.file = None


# =============================================================================
# Formatting Utilities
# =============================================================================

def format_bytes(bytes_value: int) -> str:
    """
    Format bytes as human-readable string.
    
    Args:
        bytes_value: Number of bytes
    
    Returns:
        Formatted string (e.g., "1.5 MB")
    
    Example:
        >>> format_bytes(1536)
        '1.5 KB'
        >>> format_bytes(1048576)
        '1.0 MB'
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} PB"


def format_duration(seconds: float) -> str:
    """
    Format duration as human-readable string.
    
    Args:
        seconds: Duration in seconds
    
    Returns:
        Formatted string (e.g., "1h 23m 45s")
    
    Example:
        >>> format_duration(3665)
        '1h 1m 5s'
        >>> format_duration(45.5)
        '45.5s'
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    
    delta = timedelta(seconds=seconds)
    parts = []
    
    days = delta.days
    if days:
        parts.append(f"{days}d")
    
    hours = delta.seconds // 3600
    if hours:
        parts.append(f"{hours}h")
    
    minutes = (delta.seconds % 3600) // 60
    if minutes:
        parts.append(f"{minutes}m")
    
    secs = delta.seconds % 60
    if secs or not parts:
        parts.append(f"{secs}s")
    
    return " ".join(parts)


def format_timestamp(
    dt: Optional[datetime] = None,
    format: str = "%Y-%m-%d %H:%M:%S",
) -> str:
    """
    Format timestamp.
    
    Args:
        dt: Datetime object (defaults to now)
        format: strftime format string
    
    Returns:
        Formatted timestamp
    
    Example:
        >>> format_timestamp()
        '2024-01-15 14:30:45'
    """
    if dt is None:
        dt = datetime.now()
    return dt.strftime(format)


def format_relative_time(dt: datetime) -> str:
    """
    Format datetime as relative time (e.g., "2 hours ago").
    
    Args:
        dt: Datetime object
    
    Returns:
        Relative time string
    
    Example:
        >>> from datetime import datetime, timedelta
        >>> past = datetime.now() - timedelta(hours=2)
        >>> format_relative_time(past)
        '2 hours ago'
    """
    now = datetime.now()
    diff = now - dt
    
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif seconds < 604800:
        days = int(seconds / 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"
    else:
        return dt.strftime("%Y-%m-%d")