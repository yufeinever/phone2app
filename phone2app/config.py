from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def load_config(path: str) -> Dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required. Run: python -m pip install PyYAML") from exc
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a YAML mapping: {config_path}")
    return data
