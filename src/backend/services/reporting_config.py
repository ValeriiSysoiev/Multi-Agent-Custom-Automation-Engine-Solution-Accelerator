"""Load reporting configuration for exports and Power BI refresh."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "reporting.yml"


def load_reporting_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Reporting config not found at {CONFIG_PATH}")
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("Reporting configuration must be a mapping")
    return data


__all__ = ["load_reporting_config"]
