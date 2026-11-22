"""Tests for region management CLI commands."""

import json
import tempfile
from pathlib import Path

import pytest

from auditor_toolkit.commands.region import RegionCommand


class TestRegionCommand:
    """Test region management commands."""

    def test_list_empty(self, tmp_path):
        """Test listing regions when none exist."""
        cmd = RegionCommand()
        args = type('Args', (), {
            'output_root': tmp_path,
        })()
        result = cmd._cmd_list(args)
        assert result == 0

    def test_create_region(self, tmp_path):
        """Test creating a new region."""
        cmd = RegionCommand()
        args = type('Args', (), {
            'output_root': tmp_path,
            'region': 'us-east',
            'password': 'testpassword123',
            'config': None,
        })()
        result = cmd._cmd_create(args)
        assert result == 0

        # Verify region was created
        region_dir = tmp_path / "regions" / "us-east"
        assert region_dir.is_dir()
        assert (region_dir / "portal-auth.json").is_file()

    def test_create_duplicate_region(self, tmp_path):
        """Test creating duplicate region fails."""
        cmd = RegionCommand()
        args = type('Args', (), {
            'output_root': tmp_path,
            'region': 'us-east',
            'password': 'testpassword123',
            'config': None,
        })()
        assert cmd._cmd_create(args) == 0
        assert cmd._cmd_create(args) == 1

    def test_create_region_with_config(self, tmp_path):
        """Test creating region with configuration."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"timezone": "UTC", "currency": "USD"}))

        cmd = RegionCommand()
        args = type('Args', (), {
            'output_root': tmp_path,
            'region': 'eu-west',
            'password': 'testpassword123',
            'config': config_file,
        })()
        assert cmd._cmd_create(args) == 0

        region_dir = tmp_path / "regions" / "eu-west"
        config_file = region_dir / "region-config.json"
        assert config_file.is_file()
        assert json.loads(config_file.read_text()) == {"timezone": "UTC", "currency": "USD"}

    def test_list_regions(self, tmp_path):
        """Test listing regions."""
        cmd = RegionCommand()
        # Create two regions
        for region in ["us-east", "eu-west"]:
            args = type('Args', (), {
                'output_root': tmp_path,
                'region': region,
                'password': 'testpassword123',
                'config': None,
            })()
            cmd._cmd_create(args)

        args = type('Args', (), {'output_root': tmp_path})()
        result = cmd._cmd_list(args)
        assert result == 0

    def test_config_show_none(self, tmp_path):
        """Test showing config when none exists."""
        cmd = RegionCommand()
        args = type('Args', (), {
            'output_root': tmp_path,
            'region': 'us-east',
            'password': 'testpassword123',
            'config': None,
        })()
        cmd._cmd_create(args)

        args = type('Args', (), {
            'output_root': tmp_path,
            'region': 'us-east',
            'show': True,
            'set': None,
        })()
        result = cmd._cmd_config(args)
        assert result == 0

    def test_config_set_and_show(self, tmp_path):
        """Test setting and showing region configuration."""
        cmd = RegionCommand()
        args = type('Args', (), {
            'output_root': tmp_path,
            'region': 'us-east',
            'password': 'testpassword123',
            'config': None,
        })()
        cmd._cmd_create(args)

        config_file = tmp_path / "region-config.json"
        config_file.write_text(json.dumps({"timezone": "America/New_York", "currency": "USD"}))

        # Set config
        args = type('Args', (), {
            'output_root': tmp_path,
            'region': 'us-east',
            'set': config_file,
            'show': False,
        })()
        assert cmd._cmd_config(args) == 0

        # Show config
        args = type('Args', (), {
            'output_root': tmp_path,
            'region': 'us-east',
            'show': True,
            'set': None,
        })()
        result = cmd._cmd_config(args)
        assert result == 0

    def test_config_nonexistent_region(self, tmp_path):
        """Test config for nonexistent region fails."""
        cmd = RegionCommand()
        args = type('Args', (), {
            'output_root': tmp_path,
            'region': 'nonexistent',
            'show': True,
            'set': None,
        })()
        result = cmd._cmd_config(args)
        assert result == 1

    def test_delete_region(self, tmp_path):
        """Test deleting a region."""
        cmd = RegionCommand()
        args = type('Args', (), {
            'output_root': tmp_path,
            'region': 'us-east',
            'password': 'testpassword123',
            'config': None,
        })()
        cmd._cmd_create(args)

        args = type('Args', (), {
            'output_root': tmp_path,
            'region': 'us-east',
            'force': True,
        })()
        result = cmd._cmd_delete(args)
        assert result == 0

        # Verify region is deleted
        assert not (tmp_path / "regions" / "us-east").exists()

    def test_delete_nonexistent_region(self, tmp_path):
        """Test deleting nonexistent region fails."""
        cmd = RegionCommand()
        args = type('Args', (), {
            'output_root': tmp_path,
            'region': 'nonexistent',
            'force': True,
        })()
        result = cmd._cmd_delete(args)
        assert result == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])