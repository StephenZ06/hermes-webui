"""
Regression tests for pytest-process state isolation.

Some tests import api.config/api.models during collection and directly write
sessions from the pytest process. conftest must publish the test state env vars
before those imports, not only for the server subprocess.
"""

from pathlib import Path


def test_api_config_uses_pytest_state_dir():
    import api.config as config
    from tests.conftest import TEST_STATE_DIR

    test_state_dir = TEST_STATE_DIR.resolve()
    production_state_dir = (Path.home() / ".hermes" / "webui").resolve()

    assert config.STATE_DIR == test_state_dir
    assert config.SESSION_DIR == test_state_dir / "sessions"
    assert config.STATE_DIR != production_state_dir
    assert production_state_dir not in config.SESSION_DIR.resolve().parents


def test_temp_dir_is_pinned_outside_the_test_state_dir():
    """The agent's boot hook must not be able to move the temp dir into the test home.

    Importing hermes-agent's ``hermes_bootstrap`` points TMPDIR at
    ``$HERMES_HOME/cache/scratch`` unless a temp var is already set. In the
    pytest process HERMES_HOME is TEST_STATE_DIR, which the test_server fixture
    wipes before booting the server, so every server-backed test then failed
    at setup opening its log under the deleted scratch dir.
    """
    import os
    import tempfile

    from tests.conftest import TEST_STATE_DIR

    pinned = os.environ.get("TMPDIR", "")
    assert pinned, "conftest must pin TMPDIR so the agent's scratch redirect leaves it alone"
    assert os.environ.get("HERMES_SCRATCH_DIR", "") != pinned
    temp_root = Path(tempfile.gettempdir()).resolve()
    assert temp_root != TEST_STATE_DIR and TEST_STATE_DIR not in temp_root.parents

    try:
        from hermes_constants import apply_scratch_tmp_env
    except ImportError:
        return
    env = dict(os.environ)
    assert apply_scratch_tmp_env(env) is False
    assert env["TMPDIR"] == pinned


def test_importing_bootstrap_does_not_load_the_repo_dotenv(tmp_path):
    """bootstrap.py loads REPO_ROOT/.env into os.environ at import time.

    Several tests import (or re-import) bootstrap, so a developer's real .env --
    HERMES_HOME, provider API keys -- leaked into the pytest process and stayed
    there, overriding the isolated TEST_STATE_DIR. conftest must switch the
    import-time load off for the whole run.
    """
    import os
    import shutil
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[1]
    shutil.copy(repo / "bootstrap.py", tmp_path / "bootstrap.py")
    (tmp_path / ".env").write_text("HERMES_WEBUI_TEST_DOTENV_LEAK=leaked\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "HERMES_WEBUI_TEST_DOTENV_LEAK"}
    result = subprocess.run(
        [sys.executable, "-c",
         "import os, bootstrap; print(os.environ.get('HERMES_WEBUI_TEST_DOTENV_LEAK', ''))"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""
