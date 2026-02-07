"""Configuration handling for OSTicket Helper."""

import copy
import os
import subprocess
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Optional

import yaml

_PKG = files("ostickethelper")


@dataclass
class OSTicketConfig:
    """OSTicket configuration."""
    url: str
    username: str
    password: str
    headless: bool
    inbox_dir: str
    slow_mo: int = 0
    work_dir: Path = field(default_factory=lambda: Path.cwd())
    receipts_dir: Path = field(default_factory=lambda: Path.cwd() / "receipts")
    temp_dir: Path = field(default_factory=lambda: Path.cwd() / ".tmp")
    logo_path: Optional[Path] = None
    template_path: Path = field(default_factory=lambda: Path(str(_PKG.joinpath("template.typ"))))


@dataclass
class AppConfig:
    """Application configuration."""
    osticket: OSTicketConfig
    strings: dict = field(default_factory=dict)


def decrypt_gpg_file(filepath: Path) -> str:
    """
    Decrypt a GPG-encrypted file and return its contents.

    Args:
        filepath: Path to the .gpg file.

    Returns:
        Decrypted content as string.

    Raises:
        RuntimeError: If decryption fails.
    """
    try:
        result = subprocess.run(
            ["gpg", "--decrypt", "--quiet", str(filepath)],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to decrypt {filepath}: {e.stderr}")


def _deep_merge(base: dict, override: dict) -> dict:
    """
    Deep-merge override into base (both dicts). Returns a new dict.
    Override values take precedence.
    """
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_config(config_path: Optional[str] = None, work_dir: Optional[Path] = None) -> AppConfig:
    """
    Load configuration from YAML file.

    Loads defaults from defaults.yaml first, then merges the user config on top.
    Paths in the config are resolved relative to work_dir (defaults to cwd).

    Args:
        config_path: Path to config file. Defaults to config.yaml in the same directory.
        work_dir: Working directory for resolving relative paths. Defaults to cwd.

    Returns:
        AppConfig object with loaded configuration.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        ValueError: If config is invalid.
    """
    # Load defaults from package data
    defaults_text = _PKG.joinpath("defaults.yaml").read_text(encoding="utf-8")
    defaults = yaml.safe_load(defaults_text) or {}

    # Load user config
    if config_path is None:
        config_path = Path(__file__).parent / "config.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    # Merge: user config overrides defaults
    merged = _deep_merge(defaults, data)

    if "osticket" not in merged:
        raise ValueError("Missing 'osticket' section in config")

    osticket_data = merged["osticket"]

    for field_name in ["url", "username"]:
        if field_name not in osticket_data:
            raise ValueError(f"Missing required field 'osticket.{field_name}' in config")

    # Determine work_dir
    if work_dir is None:
        if "work_dir" in osticket_data:
            resolved_work_dir = Path(osticket_data["work_dir"]).resolve()
        else:
            resolved_work_dir = Path.cwd()
    else:
        resolved_work_dir = Path(work_dir).resolve()

    # Resolve password from multiple sources (first match wins):
    # 1. OSTICKET_PASSWORD environment variable
    # 2. password field in config
    # 3. secrets_file (plain text or GPG-encrypted)
    password = os.environ.get("OSTICKET_PASSWORD")

    if not password and "password" in osticket_data:
        password = osticket_data["password"]

    if not password and "secrets_file" in osticket_data:
        secrets_path = resolved_work_dir / osticket_data["secrets_file"]
        if not secrets_path.exists():
            raise FileNotFoundError(f"Secrets file not found: {secrets_path}")
        if secrets_path.suffix == ".gpg":
            password = decrypt_gpg_file(secrets_path)
        else:
            password = secrets_path.read_text(encoding="utf-8").strip()

    if not password:
        raise ValueError(
            "No password configured. Set OSTICKET_PASSWORD environment variable, "
            "add 'password' to config, or provide 'secrets_file'."
        )

    # Resolve paths relative to work_dir
    inbox_dir = resolved_work_dir / osticket_data.get("inbox_dir", "inbox/osticket")
    receipts_dir = resolved_work_dir / osticket_data.get("receipts_dir", "receipts")
    temp_dir = resolved_work_dir / osticket_data.get("temp_dir", ".tmp")

    # Logo path: None if not specified
    logo_path = None
    if "logo_path" in osticket_data:
        logo_path = resolved_work_dir / osticket_data["logo_path"]

    # Template path: from config or package default
    template_path = Path(str(_PKG.joinpath("template.typ")))
    if "template_path" in osticket_data:
        template_path = resolved_work_dir / osticket_data["template_path"]

    osticket_config = OSTicketConfig(
        url=osticket_data["url"].rstrip("/"),
        username=osticket_data["username"],
        password=password,
        headless=osticket_data.get("headless", False),
        inbox_dir=str(inbox_dir),
        slow_mo=osticket_data.get("slow_mo", 0),
        work_dir=resolved_work_dir,
        receipts_dir=receipts_dir,
        temp_dir=temp_dir,
        logo_path=logo_path,
        template_path=template_path,
    )

    # Merge strings: defaults + user overrides
    default_strings = defaults.get("strings", {})
    user_strings = data.get("strings", {})
    strings = _deep_merge(default_strings, user_strings)

    return AppConfig(osticket=osticket_config, strings=strings)
