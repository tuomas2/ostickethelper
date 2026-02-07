"""Tests for config.py."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from ostickethelper.config import load_config, AppConfig, OSTicketConfig, _deep_merge


VALID_CONFIG = {
    "osticket": {
        "url": "https://example.com/",
        "username": "admin",
        "secrets_file": "secrets/osticket-password.txt.gpg",
        "headless": True,
        "slow_mo": 100,
        "inbox_dir": "inbox/osticket",
    }
}

VALID_CONFIG_PASSWORD = {
    "osticket": {
        "url": "https://example.com/",
        "username": "admin",
        "password": "direct-password",
        "headless": True,
        "slow_mo": 100,
        "inbox_dir": "inbox/osticket",
    }
}


def _write_yaml(path, data):
    with open(path, "w") as f:
        yaml.dump(data, f)


class TestDeepMerge:
    def test_simple_merge(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        base = {"a": {"x": 1, "y": 2}, "b": 3}
        override = {"a": {"y": 99, "z": 100}}
        result = _deep_merge(base, override)
        assert result == {"a": {"x": 1, "y": 99, "z": 100}, "b": 3}

    def test_override_does_not_mutate_base(self):
        base = {"a": {"x": 1}}
        override = {"a": {"x": 2}}
        _deep_merge(base, override)
        assert base["a"]["x"] == 1


class TestLoadConfig:
    @patch("ostickethelper.config.decrypt_gpg_file", return_value="secret-password")
    def test_valid_config(self, mock_gpg, tmp_path):
        config_file = tmp_path / "config.yaml"
        _write_yaml(config_file, VALID_CONFIG)

        # Create secrets file
        secrets_dir = tmp_path / "secrets"
        secrets_dir.mkdir()
        (secrets_dir / "osticket-password.txt.gpg").touch()

        result = load_config(str(config_file), work_dir=tmp_path)
        assert isinstance(result, AppConfig)
        assert isinstance(result.osticket, OSTicketConfig)
        assert result.osticket.url == "https://example.com"  # trailing slash stripped
        assert result.osticket.username == "admin"
        assert result.osticket.password == "secret-password"
        assert result.osticket.headless is True
        assert result.osticket.slow_mo == 100
        assert result.osticket.work_dir == tmp_path.resolve()
        mock_gpg.assert_called_once()

    @patch("ostickethelper.config.decrypt_gpg_file", return_value="secret-password")
    def test_missing_osticket_section(self, mock_gpg, tmp_path):
        # With defaults.yaml providing osticket defaults, a config without
        # osticket section still has osticket from defaults but missing
        # required fields (url, username, secrets_file)
        config_file = tmp_path / "config.yaml"
        _write_yaml(config_file, {"other": "data"})

        with pytest.raises(ValueError, match="osticket.url"):
            load_config(str(config_file), work_dir=tmp_path)

    @patch("ostickethelper.config.decrypt_gpg_file", return_value="secret-password")
    def test_missing_required_field_url(self, mock_gpg, tmp_path):
        config_file = tmp_path / "config.yaml"
        data = {"osticket": {"username": "admin", "secrets_file": "secrets/x.gpg"}}
        _write_yaml(config_file, data)

        with pytest.raises(ValueError, match="osticket.url"):
            load_config(str(config_file), work_dir=tmp_path)

    @patch("ostickethelper.config.decrypt_gpg_file", return_value="secret-password")
    def test_missing_required_field_username(self, mock_gpg, tmp_path):
        config_file = tmp_path / "config.yaml"
        data = {"osticket": {"url": "https://example.com", "secrets_file": "secrets/x.gpg"}}
        _write_yaml(config_file, data)

        with pytest.raises(ValueError, match="osticket.username"):
            load_config(str(config_file), work_dir=tmp_path)

    def test_missing_password_entirely(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        data = {"osticket": {"url": "https://example.com", "username": "admin"}}
        _write_yaml(config_file, data)

        with pytest.raises(ValueError, match="No password configured"):
            load_config(str(config_file), work_dir=tmp_path)

    def test_missing_config_file(self):
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            load_config("/nonexistent/config.yaml")

    @patch("ostickethelper.config.decrypt_gpg_file", return_value="secret-password")
    def test_missing_secrets_file(self, mock_gpg, tmp_path):
        config_file = tmp_path / "config.yaml"
        data = {
            "osticket": {
                "url": "https://example.com",
                "username": "admin",
                "secrets_file": "secrets/nonexistent.gpg",
            }
        }
        _write_yaml(config_file, data)

        with pytest.raises(FileNotFoundError, match="Secrets file not found"):
            load_config(str(config_file), work_dir=tmp_path)

    @patch("ostickethelper.config.decrypt_gpg_file", return_value="secret-password")
    def test_url_trailing_slash_stripped(self, mock_gpg, tmp_path):
        config_file = tmp_path / "config.yaml"
        data = {
            "osticket": {
                "url": "https://example.com/path/",
                "username": "admin",
                "secrets_file": "secrets/osticket-password.txt.gpg",
                "headless": True,
                "slow_mo": 100,
                "inbox_dir": "inbox/osticket",
            }
        }
        _write_yaml(config_file, data)

        secrets_dir = tmp_path / "secrets"
        secrets_dir.mkdir()
        (secrets_dir / "osticket-password.txt.gpg").touch()

        result = load_config(str(config_file), work_dir=tmp_path)
        assert result.osticket.url == "https://example.com/path"

    @patch("ostickethelper.config.decrypt_gpg_file", return_value="secret-password")
    def test_default_values(self, mock_gpg, tmp_path):
        config_file = tmp_path / "config.yaml"
        # Minimal config without optional fields
        data = {
            "osticket": {
                "url": "https://example.com",
                "username": "admin",
                "secrets_file": "secrets/osticket-password.txt.gpg",
            }
        }
        _write_yaml(config_file, data)

        secrets_dir = tmp_path / "secrets"
        secrets_dir.mkdir()
        (secrets_dir / "osticket-password.txt.gpg").touch()

        result = load_config(str(config_file), work_dir=tmp_path)
        assert result.osticket.headless is True  # from defaults.yaml
        assert result.osticket.slow_mo == 0
        assert "inbox/osticket" in result.osticket.inbox_dir

    @patch("ostickethelper.config.decrypt_gpg_file", return_value="secret-password")
    def test_strings_loaded_from_defaults(self, mock_gpg, tmp_path):
        config_file = tmp_path / "config.yaml"
        data = {
            "osticket": {
                "url": "https://example.com",
                "username": "admin",
                "secrets_file": "secrets/osticket-password.txt.gpg",
            }
        }
        _write_yaml(config_file, data)

        secrets_dir = tmp_path / "secrets"
        secrets_dir.mkdir()
        (secrets_dir / "osticket-password.txt.gpg").touch()

        result = load_config(str(config_file), work_dir=tmp_path)
        # Should have defaults loaded (English)
        assert "formatter" in result.strings
        assert result.strings["formatter"]["no_open_tickets"] == "No open tickets."

    @patch("ostickethelper.config.decrypt_gpg_file", return_value="secret-password")
    def test_strings_override(self, mock_gpg, tmp_path):
        config_file = tmp_path / "config.yaml"
        data = {
            "osticket": {
                "url": "https://example.com",
                "username": "admin",
                "secrets_file": "secrets/osticket-password.txt.gpg",
            },
            "strings": {
                "formatter": {
                    "no_open_tickets": "Ei avoimia tikettejä.",
                }
            }
        }
        _write_yaml(config_file, data)

        secrets_dir = tmp_path / "secrets"
        secrets_dir.mkdir()
        (secrets_dir / "osticket-password.txt.gpg").touch()

        result = load_config(str(config_file), work_dir=tmp_path)
        # Overridden value
        assert result.strings["formatter"]["no_open_tickets"] == "Ei avoimia tikettejä."
        # Non-overridden value from defaults
        assert result.strings["formatter"]["total"] == "Total: {count} tickets"

    @patch("ostickethelper.config.decrypt_gpg_file", return_value="secret-password")
    def test_paths_resolved_relative_to_work_dir(self, mock_gpg, tmp_path):
        config_file = tmp_path / "config.yaml"
        data = {
            "osticket": {
                "url": "https://example.com",
                "username": "admin",
                "secrets_file": "secrets/osticket-password.txt.gpg",
                "inbox_dir": "my/inbox",
                "receipts_dir": "my/receipts",
                "temp_dir": "my/tmp",
                "logo_path": "resources/logo.png",
            }
        }
        _write_yaml(config_file, data)

        secrets_dir = tmp_path / "secrets"
        secrets_dir.mkdir()
        (secrets_dir / "osticket-password.txt.gpg").touch()

        result = load_config(str(config_file), work_dir=tmp_path)
        resolved = tmp_path.resolve()
        assert result.osticket.inbox_dir == str(resolved / "my/inbox")
        assert result.osticket.receipts_dir == resolved / "my/receipts"
        assert result.osticket.temp_dir == resolved / "my/tmp"
        assert result.osticket.logo_path == resolved / "resources/logo.png"

    @patch("ostickethelper.config.decrypt_gpg_file", return_value="secret-password")
    def test_no_logo_path(self, mock_gpg, tmp_path):
        config_file = tmp_path / "config.yaml"
        data = {
            "osticket": {
                "url": "https://example.com",
                "username": "admin",
                "secrets_file": "secrets/osticket-password.txt.gpg",
            }
        }
        _write_yaml(config_file, data)

        secrets_dir = tmp_path / "secrets"
        secrets_dir.mkdir()
        (secrets_dir / "osticket-password.txt.gpg").touch()

        result = load_config(str(config_file), work_dir=tmp_path)
        assert result.osticket.logo_path is None


class TestPasswordSources:
    """Test different password authentication methods."""

    def test_password_from_config(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        _write_yaml(config_file, VALID_CONFIG_PASSWORD)

        result = load_config(str(config_file), work_dir=tmp_path)
        assert result.osticket.password == "direct-password"

    def test_password_from_env_var(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        data = {"osticket": {"url": "https://example.com", "username": "admin"}}
        _write_yaml(config_file, data)

        with patch.dict(os.environ, {"OSTICKET_PASSWORD": "env-password"}):
            result = load_config(str(config_file), work_dir=tmp_path)
        assert result.osticket.password == "env-password"

    def test_env_var_takes_precedence_over_config(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        _write_yaml(config_file, VALID_CONFIG_PASSWORD)

        with patch.dict(os.environ, {"OSTICKET_PASSWORD": "env-password"}):
            result = load_config(str(config_file), work_dir=tmp_path)
        assert result.osticket.password == "env-password"

    @patch("ostickethelper.config.decrypt_gpg_file", return_value="gpg-password")
    def test_env_var_takes_precedence_over_secrets_file(self, mock_gpg, tmp_path):
        config_file = tmp_path / "config.yaml"
        _write_yaml(config_file, VALID_CONFIG)

        secrets_dir = tmp_path / "secrets"
        secrets_dir.mkdir()
        (secrets_dir / "osticket-password.txt.gpg").touch()

        with patch.dict(os.environ, {"OSTICKET_PASSWORD": "env-password"}):
            result = load_config(str(config_file), work_dir=tmp_path)
        assert result.osticket.password == "env-password"
        mock_gpg.assert_not_called()

    def test_plain_text_secrets_file(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        data = {
            "osticket": {
                "url": "https://example.com",
                "username": "admin",
                "secrets_file": "secrets/password.txt",
            }
        }
        _write_yaml(config_file, data)

        secrets_dir = tmp_path / "secrets"
        secrets_dir.mkdir()
        (secrets_dir / "password.txt").write_text("plain-password\n")

        result = load_config(str(config_file), work_dir=tmp_path)
        assert result.osticket.password == "plain-password"

    @patch("ostickethelper.config.decrypt_gpg_file", return_value="gpg-password")
    def test_gpg_secrets_file(self, mock_gpg, tmp_path):
        config_file = tmp_path / "config.yaml"
        _write_yaml(config_file, VALID_CONFIG)

        secrets_dir = tmp_path / "secrets"
        secrets_dir.mkdir()
        (secrets_dir / "osticket-password.txt.gpg").touch()

        result = load_config(str(config_file), work_dir=tmp_path)
        assert result.osticket.password == "gpg-password"
        mock_gpg.assert_called_once()

    def test_missing_secrets_file(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        data = {
            "osticket": {
                "url": "https://example.com",
                "username": "admin",
                "secrets_file": "secrets/nonexistent.gpg",
            }
        }
        _write_yaml(config_file, data)

        with pytest.raises(FileNotFoundError, match="Secrets file not found"):
            load_config(str(config_file), work_dir=tmp_path)
