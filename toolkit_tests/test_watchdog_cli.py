import pytest

from auditor_toolkit.cli import main


def test_watchdog_restricts_snapshot_root(tmp_path, monkeypatch, capsys):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)

    with pytest.raises(SystemExit) as error:
        main(["watchdog", "example.test", "--output-root", str(tmp_path)])
    assert error.value.code == 2
    assert "inside the current workspace" in capsys.readouterr().err

    assert main(["watchdog", "example.test", "--output-root", "reports"]) == 1
    assert "No audit found" in capsys.readouterr().out
