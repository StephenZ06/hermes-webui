"""The pytest process must keep pointing HERMES_WEBUI_STATE_DIR at the test
state dir for the whole run. If a test drops it, any later subprocess that
imports api.config falls back to the REAL ~/.hermes/webui while still carrying
the test HERMES_WEBUI_DEFAULT_WORKSPACE — and startup reconciliation writes
that /tmp test path into the user's real settings.json."""
import os

from tests.conftest import TEST_STATE_DIR


def test_state_dir_env_still_points_at_the_test_state_dir():
    assert os.environ.get("HERMES_WEBUI_STATE_DIR") == str(TEST_STATE_DIR)
