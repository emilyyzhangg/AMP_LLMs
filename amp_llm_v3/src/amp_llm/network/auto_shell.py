"""Auto shell detector and wrapper for SSH sessions."""

import logging
from .config import SHELL_PROMPTS, SHELL_SILENT_PREFIX
from .utils import detect_shell_type

logger = logging.getLogger(__name__)


class RemoteShellProfile:
    """Encapsulates detected shell type and prompt formatting."""

    def __init__(self, shell_name: str, prompt_fmt: str, silent_prefix: str):
        self.shell_name = shell_name
        self.prompt_fmt = prompt_fmt
        self.silent_prefix = silent_prefix


async def detect_remote_shell(ssh) -> RemoteShellProfile:
    """
    Detects remote user shell and returns appropriate profile.
    
    Args:
        ssh: Active SSH connection
        
    Returns:
        RemoteShellProfile with shell configuration
    """
    shell_name = await detect_shell_type(ssh)
    prompt_fmt = SHELL_PROMPTS.get(shell_name, SHELL_PROMPTS['default'])
    
    return RemoteShellProfile(
        shell_name=shell_name,
        prompt_fmt=prompt_fmt,
        silent_prefix=SHELL_SILENT_PREFIX
    )