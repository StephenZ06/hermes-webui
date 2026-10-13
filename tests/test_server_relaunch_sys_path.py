"""server.py must import its own ``api`` package when re-executed by the agent.

hermes-agent >= 0.21.7 re-execs a process whose interpreter is not its managed
one as ``python -I -c "...runpy.run_path('<server.py>')"``. ``-I`` drops the
current directory and PYTHONPATH, and ``run_path`` does not add the script's
directory to ``sys.path`` — so ``from api.auth import ...`` failed and the
WebUI crash-looped after an agent update.
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_server_module_imports_under_isolated_run_path(tmp_path):
    code = (
        "import runpy, sys; "
        f"runpy.run_path({str(ROOT / 'server.py')!r}, run_name='relaunch_probe')"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert "No module named 'api'" not in result.stderr, result.stderr[-2000:]
    assert result.returncode == 0, result.stderr[-2000:]
