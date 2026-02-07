"""Shared fixtures for ostickethelper tests."""

from pathlib import Path

import pytest
import yaml

from ostickethelper.config import OSTicketConfig


@pytest.fixture(scope="session")
def default_strings():
    """Load strings from package defaults.yaml."""
    from importlib.resources import files

    _PKG = files("ostickethelper")
    defaults_text = _PKG.joinpath("defaults.yaml").read_text(encoding="utf-8")
    defaults = yaml.safe_load(defaults_text)
    return defaults["strings"]


def make_config(tmp_path, logo=False):
    """Create a test OSTicketConfig pointing to tmp_path."""
    from importlib.resources import files

    logo_path = None
    if logo:
        logo_path = tmp_path / "logo.png"
        from PIL import Image
        img = Image.new("RGB", (10, 10), "red")
        img.save(str(logo_path), "PNG")

    return OSTicketConfig(
        url="https://example.com",
        username="test",
        password="test",
        headless=True,
        inbox_dir=str(tmp_path / "inbox"),
        slow_mo=0,
        work_dir=tmp_path,
        receipts_dir=tmp_path / "receipts",
        temp_dir=tmp_path / "tmp",
        logo_path=logo_path,
        template_path=Path(str(files("ostickethelper").joinpath("template.typ"))),
    )
