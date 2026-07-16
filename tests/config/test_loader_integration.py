"""
Integration tests for configuration loader with recovery system.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import pytest


# Import after setting environment to avoid module-level CONFIG_FILE creation
def setup_test_config_path(tmp_path):
    """Setup test config path before importing loader."""
    import os

    os.environ["HTML2MD_CONFIG_PATH"] = str(tmp_path / "config.json")


class TestLoaderIntegration:
    """Integration tests for loader with backup and recovery."""

    @pytest.fixture(autouse=True)
    def setup_env(self, tmp_path, monkeypatch):
        """Setup test environment with isolated config path."""
        test_config = tmp_path / "config.json"
        monkeypatch.setenv("HTML2MD_CONFIG_PATH", str(test_config))

        # Force reload of loader module to pick up new env var
        import sys

        if "html2md.config.loader" in sys.modules:
            del sys.modules["html2md.config.loader"]
        if "html2md.config.backup" in sys.modules:
            del sys.modules["html2md.config.backup"]
        if "html2md.config.recovery" in sys.modules:
            del sys.modules["html2md.config.recovery"]

        yield

        # Cleanup
        for module in list(sys.modules.keys()):
            if module.startswith("html2md.config"):
                del sys.modules[module]

    def test_save_config_creates_file(self, tmp_path):
        """Test save_config creates config file if it doesn't exist."""
        from html2md.config.loader import save_config, CONFIG_FILE

        test_data = {"test": "data", "version": 1}
        save_config(test_data)

        assert CONFIG_FILE.exists()
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            saved_data = json.load(f)
        assert saved_data["test"] == "data"

    def test_save_and_load_roundtrip(self, tmp_path):
        """Test saving and loading config maintains data integrity."""
        from html2md.config.loader import save_config, load_config

        original_data = {
            "domains": {"example.com": {"footer_marker": "test"}},
            "logging": {"level": "DEBUG"},
        }

        save_config(original_data)
        loaded_data = load_config(force_reload=True)

        assert loaded_data["domains"] == original_data["domains"]
        assert loaded_data["logging"] == original_data["logging"]

    def test_load_config_creates_default_if_missing(self, tmp_path):
        """Test load_config creates default config if file doesn't exist."""
        from html2md.config.loader import load_config, CONFIG_FILE

        config = load_config()

        assert CONFIG_FILE.exists()
        # Should contain default structure
        assert "domains" in config
        assert "logging" in config

    @mock.patch("sys.stdin.isatty", return_value=False)
    @mock.patch("sys.stdout.isatty", return_value=False)
    def test_load_corrupt_config_non_interactive_uses_defaults(
        self, mock_stdout, mock_stdin, tmp_path
    ):
        """Test loading corrupt config in non-interactive mode uses defaults."""
        from html2md.config.loader import load_config, CONFIG_FILE, DEFAULT_CONFIG

        # Create corrupt config
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write('{"invalid": json}')

        config = load_config()

        # Should return defaults
        assert config == DEFAULT_CONFIG

        # Corrupt file should still exist (not overwritten in non-interactive)
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        assert '{"invalid": json}' in content

    @mock.patch("sys.stdin.isatty", return_value=False)
    @mock.patch("sys.stdout.isatty", return_value=False)
    def test_load_corrupt_config_with_backup_restores(
        self, mock_stdout, mock_stdin, tmp_path
    ):
        """Test loading corrupt config with backup available restores from backup."""
        from html2md.config.loader import (
            load_config,
            save_config,
            get_backup_manager,
            CONFIG_FILE,
        )

        # Save valid config
        original_data = {"original": True, "version": 1}
        save_config(original_data)

        # Create backup
        backup_mgr = get_backup_manager()
        backup_mgr.create_backup(reason="test")

        # Corrupt the config
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write('{"corrupt": json}')

        # Load should restore from backup
        config = load_config(force_reload=True)

        assert config["original"] is True
        assert config["version"] == 1

    @mock.patch("sys.stdin.isatty", return_value=False)
    @mock.patch("sys.stdout.isatty", return_value=False)
    def test_load_corrupt_config_saves_corrupt_file(
        self, mock_stdout, mock_stdin, tmp_path
    ):
        """Test loading corrupt config saves .corrupt file for debugging."""
        from html2md.config.loader import load_config, CONFIG_FILE

        # Create corrupt config
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write('{"invalid": json}')

        load_config()

        # Check .corrupt file was created
        corrupt_file = CONFIG_FILE.with_suffix(".json.corrupt")
        assert corrupt_file.exists()
        with open(corrupt_file, "r", encoding="utf-8") as f:
            content = f.read()
        assert '{"invalid": json}' in content

    def test_save_config_validates_data(self, tmp_path):
        """Test save_config validates config data before saving."""
        from html2md.config.loader import save_config, load_config

        # Save incomplete config (missing required keys)
        incomplete_data = {"custom_key": "value"}
        save_config(incomplete_data)

        # Load and verify it was merged with defaults
        config = load_config(force_reload=True)

        # Should have both custom data and default keys
        assert "custom_key" in config
        assert "domains" in config  # From defaults
        assert "logging" in config  # From defaults

    def test_save_config_invalidates_cache(self, tmp_path):
        """Test save_config invalidates the config cache."""
        from html2md.config.loader import save_config, load_config

        # Load initial config
        config1 = load_config()
        initial_version = config1.get("version", 0)

        # Modify and save
        config1["version"] = initial_version + 1
        save_config(config1)

        # Load without force_reload (should get cached updated version)
        config2 = load_config()

        assert config2["version"] == initial_version + 1

    def test_cached_loads_return_independent_snapshots(self):
        """Mutating a returned config cannot mutate the shared cache."""
        from html2md.config.loader import load_config

        first = load_config()
        first["logging"]["level"] = "DEBUG"
        second = load_config()

        assert second["logging"]["level"] == "WARNING"

    def test_save_caches_an_independent_snapshot(self):
        """Mutating save input after the call cannot alter cached state."""
        from html2md.config.loader import load_config, save_config

        supplied = load_config()
        supplied["logging"]["level"] = "INFO"
        save_config(supplied)
        supplied["logging"]["level"] = "ERROR"

        assert load_config()["logging"]["level"] == "INFO"

    def test_concurrent_callers_cannot_mutate_cached_state(self):
        """Concurrent readers receive snapshots rather than shared dictionaries."""
        from html2md.config.loader import load_config

        baseline = load_config()

        def mutate_snapshot(index):
            snapshot = load_config()
            snapshot["logging"]["level"] = f"worker-{index}"
            snapshot["domains"][f"worker-{index}.test"] = {}

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(mutate_snapshot, range(32)))

        assert load_config() == baseline

    def test_invalid_save_preserves_existing_file(self):
        """Schema failure occurs before backup or replacement."""
        from html2md.config.loader import CONFIG_FILE, load_config, save_config
        from html2md.config.schema import ConfigValidationError

        valid = load_config()
        valid["cli_defaults"]["crawl"]["rate_limit"] = 30
        save_config(valid)
        original_bytes = CONFIG_FILE.read_bytes()
        valid["cli_defaults"]["crawl"]["rate_limit"] = "thirty"

        with pytest.raises(ConfigValidationError):
            save_config(valid)

        assert CONFIG_FILE.read_bytes() == original_bytes
        assert load_config()["cli_defaults"]["crawl"]["rate_limit"] == 30

    def test_invalid_persisted_value_fails_without_rewriting_user_file(self):
        """Semantic validation failure preserves persisted evidence."""
        from html2md.config.loader import CONFIG_FILE, load_config
        from html2md.config.schema import ConfigValidationError

        invalid = {"cli_defaults": {"crawl": {"rate_limit": "30"}}}
        CONFIG_FILE.write_text(json.dumps(invalid), encoding="utf-8")
        original_bytes = CONFIG_FILE.read_bytes()

        with pytest.raises(ConfigValidationError):
            load_config(force_reload=True)

        assert CONFIG_FILE.read_bytes() == original_bytes

    def test_multiple_save_operations_atomic(self, tmp_path):
        """Test multiple save operations maintain atomicity."""
        from html2md.config.loader import save_config, load_config

        # Perform multiple saves
        for i in range(5):
            config = load_config(force_reload=True)
            config["iteration"] = i
            save_config(config)

        # Final config should be valid and have last iteration
        final_config = load_config(force_reload=True)
        assert final_config["iteration"] == 4

    def test_concurrent_load_after_save(self, tmp_path):
        """Test loading after save returns updated data."""
        from html2md.config.loader import save_config, load_config

        # Save config
        data1 = {"value": "first"}
        save_config(data1)

        # Load
        loaded1 = load_config(force_reload=True)
        assert loaded1["value"] == "first"

        # Save again with different data
        data2 = {"value": "second"}
        save_config(data2)

        # Load again
        loaded2 = load_config(force_reload=True)
        assert loaded2["value"] == "second"

    def test_get_backup_manager_singleton(self, tmp_path):
        """Test get_backup_manager returns same instance."""
        from html2md.config.loader import get_backup_manager

        mgr1 = get_backup_manager()
        mgr2 = get_backup_manager()

        assert mgr1 is mgr2

    def test_get_recovery_handler_singleton(self, tmp_path):
        """Test get_recovery_handler returns same instance."""
        from html2md.config.loader import get_recovery_handler

        handler1 = get_recovery_handler()
        handler2 = get_recovery_handler()

        assert handler1 is handler2

    @mock.patch("sys.stdin.isatty", return_value=True)
    @mock.patch("sys.stdout.isatty", return_value=True)
    @mock.patch("html2md.config.recovery.Confirm.ask", return_value=True)
    @mock.patch("html2md.config.recovery.Prompt.ask", return_value="d")
    def test_load_corrupt_interactive_confirms_before_reset(
        self, mock_prompt, mock_confirm, mock_stdout, mock_stdin, tmp_path
    ):
        """Test interactive mode requires confirmation before resetting config."""
        from html2md.config.loader import load_config, CONFIG_FILE, DEFAULT_CONFIG

        # Create corrupt config
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write('{"invalid": json}')

        load_config()

        # Should have prompted for confirmation
        assert mock_confirm.called

        # Config should be reset to defaults
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            saved_config = json.load(f)

        assert saved_config == DEFAULT_CONFIG
