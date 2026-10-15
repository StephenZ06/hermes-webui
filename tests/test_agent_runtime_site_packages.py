"""The agent bootstrap must not leave the server on another interpreter's packages."""
import os
import sys
import sysconfig

from api import config as agent_runtime


def _managed_entry(tmp_path):
    entry = tmp_path / "installs" / "k" / "environments" / "e" / "venv" / "lib" / "python3.99" / "site-packages"
    entry.mkdir(parents=True)
    return str(entry)


def test_foreign_managed_site_packages_are_dropped_and_own_restored(tmp_path, monkeypatch):
    foreign = _managed_entry(tmp_path)
    own = sysconfig.get_paths()["purelib"]
    path = [entry for entry in sys.path if entry != own] + [foreign]
    monkeypatch.setattr(sys, "path", path)
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(["/keep/me", foreign]))

    agent_runtime.keep_server_interpreter_packages()

    assert foreign not in sys.path
    assert own in sys.path
    assert os.environ["PYTHONPATH"] == "/keep/me"


def test_matching_interpreter_entries_are_left_alone(tmp_path, monkeypatch):
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    same = tmp_path / "installs" / "k" / "environments" / "e" / "venv" / "lib" / version / "site-packages"
    same.mkdir(parents=True)
    monkeypatch.setattr(sys, "path", list(sys.path) + [str(same)])
    monkeypatch.delenv("PYTHONPATH", raising=False)

    agent_runtime.keep_server_interpreter_packages()

    assert str(same) in sys.path
    assert "PYTHONPATH" not in os.environ
