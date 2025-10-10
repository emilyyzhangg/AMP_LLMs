"""Network module configuration constants."""

# SSH defaults
SSH_KEEPALIVE_INTERVAL = 15
SSH_KEEPALIVE_COUNT_MAX = 3
SSH_CONNECT_TIMEOUT = 30

# Tunnel defaults
DEFAULT_TUNNEL_REMOTE_HOST = 'localhost'
DEFAULT_TUNNEL_REMOTE_PORT = 11434

# Shell prompts
SHELL_PROMPTS = {
    'zsh': '{user}@{host} ~ % ',
    'bash': '[{user}@{host} ~]$ ',
    'fish': '{user}@{host} ~> ',
    'default': '[{user}@{host} ~]$ '
}

# Shell silent prefixes
SHELL_SILENT_PREFIX = 'bash -lc "{cmd}"'