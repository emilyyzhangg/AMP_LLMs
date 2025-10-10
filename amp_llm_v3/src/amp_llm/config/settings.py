"""
Configuration management for AMP_LLM application.
Supports environment variables with sensible defaults.
"""
import os
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass
class NetworkConfig:
    """Network and SSH configuration."""
    default_ip: str = field(default_factory=lambda: os.getenv('SSH_DEFAULT_IP', '100.99.162.98'))
    default_username: str = field(default_factory=lambda: os.getenv('SSH_DEFAULT_USERNAME', 'emilyzhang'))
    ping_timeout: float = 1.0
    ssh_timeout: int = 30
    ssh_keepalive_interval: int = 15
    ssh_keepalive_count_max: int = 3
    max_auth_attempts: int = 3

@dataclass
class CLIConfig:
    """CLI display configuration."""
    use_rich: bool = field(default_factory=lambda: os.getenv('CLI_USE_RICH', 'true').lower() == 'true')
    color_output: bool = field(default_factory=lambda: os.getenv('CLI_COLOR_OUTPUT', 'true').lower() == 'true')
    table_width: int = field(default_factory=lambda: int(os.getenv('CLI_TABLE_WIDTH', '120')))

@dataclass
class APIConfig:
    """API client configuration for external services."""
    timeout: int = 15
    max_retries: int = 3
    rate_limit_delay: float = 0.34
    max_concurrent: int = 5
    cli: CLIConfig = field(default_factory=CLIConfig)
    user_agent: str = field(
        default_factory=lambda: os.getenv(
            'API_USER_AGENT',
            'AMP_LLM/3.0 (Research Tool; +https://github.com/yourorg/amp_llm)'
        )
    )
    
    ncbi_api_key: Optional[str] = field(default_factory=lambda: os.getenv('NCBI_API_KEY'))
    

@dataclass
class LLMConfig:
    """LLM-related configuration."""
    default_model: Optional[str] = field(default_factory=lambda: os.getenv('OLLAMA_DEFAULT_MODEL'))
    timeout: int = 120
    stream_chunk_size: int = 1024
    idle_timeout: int = 3


@dataclass
class OutputConfig:
    """Output and logging configuration."""
    output_dir: Path = field(default_factory=lambda: Path(os.getenv('OUTPUT_DIR', 'output')))
    log_file: Path = field(default_factory=lambda: Path(os.getenv('LOG_FILE', 'amp_llm.log')))
    log_level: str = field(default_factory=lambda: os.getenv('LOG_LEVEL', 'INFO'))
    log_format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'


@dataclass
class AppConfig:
    """Main application configuration."""
    network: NetworkConfig = field(default_factory=NetworkConfig)
    api: APIConfig = field(default_factory=APIConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    
    def __post_init__(self):
        """Ensure directories exist and validate configuration."""
        # Create output directory
        self.output.output_dir.mkdir(exist_ok=True, parents=True)
        
        # Validate configuration
        errors = self.validate()
        if errors:
            raise ValueError(f"Configuration validation failed:\n  - " + "\n  - ".join(errors))
    
    def validate(self) -> list:
        """Validate configuration values. Returns list of errors (empty if valid)."""
        errors = []
        
        if self.api.timeout <= 0:
            errors.append("API timeout must be positive")
        
        if self.api.max_retries < 0:
            errors.append("Max retries cannot be negative")
        
        if self.api.rate_limit_delay < 0:
            errors.append("Rate limit delay cannot be negative")
        
        if self.network.ping_timeout <= 0:
            errors.append("Ping timeout must be positive")
        
        if self.network.max_auth_attempts <= 0:
            errors.append("Max auth attempts must be positive")
        
        if self.llm.timeout <= 0:
            errors.append("LLM timeout must be positive")
        
        # Validate log level
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if self.output.log_level.upper() not in valid_levels:
            errors.append(f"Invalid log level. Must be one of: {', '.join(valid_levels)}")
        
        return errors
    
    def setup_logging(self):
        """Configure logging based on settings."""
        logging.basicConfig(
            level=getattr(logging, self.output.log_level.upper()),
            format=self.output.log_format,
            handlers=[
                logging.FileHandler(self.output.log_file),
                logging.StreamHandler()
            ]
        )


# Global configuration instance
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Get the global configuration instance (singleton pattern)."""
    global _config
    if _config is None:
        _config = AppConfig()
        _config.setup_logging()
    return _config


def reload_config():
    """Reload configuration from environment (useful for testing)."""
    global _config
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except ImportError:
        pass
    _config = AppConfig()
    _config.setup_logging()
    return _config


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance. Ensures config is loaded."""
    get_config()  # Ensure logging is configured
    return logging.getLogger(name)