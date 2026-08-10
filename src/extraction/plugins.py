"""Per-format parsing plugins — the documented interface for adding a remittance
format.

A "format plugin" is a retailer/distributor remittance layout the parser knows
how to read. Historically the four built-in formats (Walmart, Costco, UNFI, KeHE)
were hardcoded: a detection list in ``pdf_extractor.py`` and a closed
``RetailerFormat`` enum. Adding a client's format meant forking that code.

This module makes a format a **config drop-in**. A plugin is described entirely
by two YAML files under a config directory:

  * ``format_configs/<name>.yml`` — ``header_pattern`` (the page-1 substring that
    identifies the format), ``column_mapping`` (deduction table column indices),
    ``amount_format`` (``plain`` or ``parenthesized``), optional ``display_name``
    and ``header_labels``.
  * ``reason_codes/<name>.yml`` — ``codes: {code: {category, description}}``.

To add a client format: drop those two files into the client's config directory.
``discover_plugins(config_dir)`` finds it; ``detect_plugin`` matches it by header
pattern; the shared parser (``pdf_extractor.extract_*``) reads it using the config.
No enum edit, no code fork.

The four built-in formats are themselves plugins (their configs live in
``src/config``); they resolve to ``RetailerFormat`` members so the demo path is
byte-for-byte unchanged.

Documented interface (the plugin contract):

    class FormatPlugin(Protocol):
        name: str                 # config stem, e.g. "walmart" or "acme_grocery"
        display_name: str         # human-facing name for the deliverable
        header_pattern: str       # page-1 substring that identifies the format
        def matches(text: str) -> bool
        @property format_config -> dict     # column_mapping, amount_format, header_labels
        @property reason_codes -> dict[str, dict]
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

import yaml

DEFAULT_CONFIG_DIR = Path(__file__).parent.parent / "config"


@runtime_checkable
class FormatPlugin(Protocol):
    name: str
    display_name: str
    header_pattern: str

    def matches(self, first_page_text: str) -> bool: ...

    @property
    def format_config(self) -> dict: ...

    @property
    def reason_codes(self) -> dict: ...


@dataclass(frozen=True)
class ConfigFormatPlugin:
    """A format plugin defined entirely by its two config files."""

    name: str
    display_name: str
    header_pattern: str
    config_dir: Path = DEFAULT_CONFIG_DIR

    def matches(self, first_page_text: str) -> bool:
        return bool(self.header_pattern) and self.header_pattern in first_page_text

    @property
    def format_config(self) -> dict:
        path = self.config_dir / "format_configs" / f"{self.name}.yml"
        if not path.exists():
            raise FileNotFoundError(f"No format config for {self.name}: {path}")
        with open(path) as f:
            return yaml.safe_load(f)

    @property
    def reason_codes(self) -> dict:
        path = self.config_dir / "reason_codes" / f"{self.name}.yml"
        if not path.exists():
            return {}
        with open(path) as f:
            return (yaml.safe_load(f) or {}).get("codes", {})


def _display_name_for(name: str, cfg: dict) -> str:
    explicit = cfg.get("display_name")
    if explicit:
        return str(explicit)
    # Built-in acronym/camelCase names keep their casing; others title-case.
    known = {"walmart": "Walmart", "costco": "Costco", "unfi": "UNFI", "keHE": "KeHE"}
    return known.get(name, name.replace("_", " ").title())


def discover_plugins(config_dir: Path = DEFAULT_CONFIG_DIR) -> list[ConfigFormatPlugin]:
    """Discover every format plugin under ``config_dir/format_configs/*.yml``.

    A config without a ``header_pattern`` is skipped (it cannot be detected).
    Sorted by name for deterministic detection order.
    """
    fmt_dir = Path(config_dir) / "format_configs"
    plugins: list[ConfigFormatPlugin] = []
    if not fmt_dir.exists():
        return plugins
    for path in sorted(fmt_dir.glob("*.yml")):
        with open(path) as f:
            cfg = yaml.safe_load(f) or {}
        header_pattern = cfg.get("header_pattern")
        if not header_pattern:
            continue
        name = cfg.get("retailer") or path.stem
        plugins.append(ConfigFormatPlugin(
            name=str(name),
            display_name=_display_name_for(str(name), cfg),
            header_pattern=str(header_pattern),
            config_dir=Path(config_dir),
        ))
    return plugins


def detect_plugin(first_page_text: str,
                  config_dir: Path = DEFAULT_CONFIG_DIR) -> Optional[ConfigFormatPlugin]:
    """Return the first discovered plugin whose header pattern matches, or None."""
    for plugin in discover_plugins(config_dir):
        if plugin.matches(first_page_text):
            return plugin
    return None
