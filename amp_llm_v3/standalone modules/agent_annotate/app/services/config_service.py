"""
Configuration service - loads, caches, and manages the YAML pipeline config.
"""

import hashlib
import yaml
from pathlib import Path
from typing import Optional

from app.config import DEFAULT_CONFIG_PATH
from app.models.config_models import AnnotationConfig


class ConfigService:
    """Loads default_config.yaml, allows runtime overrides, and provides snapshots."""

    def __init__(self):
        self._config: Optional[AnnotationConfig] = None
        self._raw: dict = {}
        self._config_hash: str = ""

    def load(self, path: Path = DEFAULT_CONFIG_PATH) -> AnnotationConfig:
        """Load (or reload) configuration from YAML."""
        with open(path, "r") as f:
            raw = yaml.safe_load(f)
        self._raw = raw or {}
        self._config = AnnotationConfig(**self._raw)
        self._config_hash = hashlib.sha256(
            yaml.dump(self._raw, sort_keys=True).encode()
        ).hexdigest()[:12]
        return self._config

    def get(self) -> AnnotationConfig:
        """Return the current config, loading defaults if needed."""
        if self._config is None:
            self.load()
        return self._config  # type: ignore

    def get_hash(self) -> str:
        """Return a short hash of the current config for versioning."""
        if not self._config_hash:
            self.load()
        return self._config_hash

    def update(self, overrides: dict) -> AnnotationConfig:
        """Merge overrides into the current config and return it."""
        merged = {**self._raw, **overrides}
        self._raw = merged
        self._config = AnnotationConfig(**merged)
        self._config_hash = hashlib.sha256(
            yaml.dump(merged, sort_keys=True).encode()
        ).hexdigest()[:12]
        return self._config

    def snapshot(self) -> dict:
        """Return a serialisable copy of the config for freezing into a job."""
        return self._raw.copy()


# Module-level singleton
config_service = ConfigService()
