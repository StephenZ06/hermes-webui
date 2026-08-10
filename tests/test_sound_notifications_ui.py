"""Sound notification system (Priority 3) wiring guards.

hermes-webui already had a synthesized Web Audio API chime mechanism
(playNotificationSound/playAttentionSound) gated by a single existing
`sound_enabled` toggle before this change -- these tests pin the three new
chime kinds (agent failed / agent spawned / thinking tick) that extend that
same mechanism, and guard against a second, parallel toggle being invented.
See docs/HERMES_STUDIO_PARITY_PLAN.md, "Sound notification system".
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MESSAGES_JS = (ROOT / "static" / "messages.js").read_text(encoding="utf-8")
INDEX_HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
CONFIG_PY = (ROOT / "api" / "config.py").read_text(encoding="utf-8")


def _function_body(source, signature):
    idx = source.index(signature)
    end = source.index("\nfunction ", idx + 1)
    return source[idx:end]


def test_three_new_sound_functions_exist_and_are_gated():
    for fn in ("playFailureSound", "playAgentSpawnedSound", "playThinkingTickSound"):
        assert f"function {fn}(" in MESSAGES_JS, f"{fn} not defined"
        body = _function_body(MESSAGES_JS, f"function {fn}(")
        assert "if(!window._soundEnabled) return;" in body, (
            f"{fn} must be gated by the existing window._soundEnabled toggle"
        )


def test_failure_sound_uses_web_audio_oscillator_not_an_audio_file():
    body = _function_body(MESSAGES_JS, "function playFailureSound(")
    assert "createOscillator" in body
    assert "new Audio(" not in body


def test_apperror_handler_plays_failure_sound_except_when_cancelled():
    idx = MESSAGES_JS.index("source.addEventListener('apperror',e=>{")
    end = MESSAGES_JS.index("\n    source.addEventListener('warning'", idx)
    body = MESSAGES_JS[idx:end]
    assert "playFailureSound()" in body
    # The call must be conditioned on the event NOT being a user-initiated
    # cancel -- an explicit Stop click must stay silent.
    call_idx = body.index("playFailureSound()")
    line_start = body.rindex("\n", 0, call_idx)
    guard_line = body[line_start:call_idx]
    assert "cancelled" in guard_line, (
        "playFailureSound() call site must be guarded against d.type==='cancelled'"
    )


def test_server_turn_started_handler_plays_agent_spawned_sound():
    idx = MESSAGES_JS.index("es.addEventListener('server_turn_started'")
    end = MESSAGES_JS.index("\n    });", idx)
    body = MESSAGES_JS[idx:end]
    assert "playAgentSpawnedSound()" in body
    # Must not fire on a recovered (reconnect-replay) frame -- that is not a
    # new spawn.
    call_idx = body.index("playAgentSpawnedSound()")
    preceding_line_start = body.rindex("\n", 0, call_idx)
    guard_line = body[preceding_line_start:call_idx]
    assert "!recovered" in guard_line or "recovered" in guard_line


def test_reasoning_handler_plays_thinking_tick_sound():
    idx = MESSAGES_JS.index("source.addEventListener('reasoning',e=>{")
    end = MESSAGES_JS.index("\n    });", idx)
    body = MESSAGES_JS[idx:end]
    assert "playThinkingTickSound(streamId)" in body


def test_thinking_tick_only_fires_when_backgrounded_and_deduped_per_stream():
    body = _function_body(MESSAGES_JS, "function playThinkingTickSound(")
    assert "_isBackgroundedForBrowserNotification()" in body, (
        "thinking tick must not fire while the tab/turn is actively being watched"
    )
    assert "_thinkingTickStreams" in body, (
        "thinking tick must be deduped per stream (not once per reasoning chunk)"
    )


def test_no_second_sound_toggle_was_invented():
    """Regression guard: the three new chime kinds must ride the existing
    sound_enabled toggle, not add a parallel settings key or checkbox."""
    bool_keys_idx = CONFIG_PY.index("_SETTINGS_BOOL_KEYS = {")
    bool_keys_end = CONFIG_PY.index("\n}", bool_keys_idx)
    bool_keys_block = CONFIG_PY[bool_keys_idx:bool_keys_end]
    sound_like_keys = re.findall(r'"(\w*sound\w*)"', bool_keys_block)
    assert sound_like_keys == ["sound_enabled"], (
        f"expected only the existing sound_enabled toggle, found: {sound_like_keys}"
    )
    assert "settingsSoundEnabled" in INDEX_HTML
    assert "settingsAgentSpawnedSound" not in INDEX_HTML
    assert "settingsFailureSound" not in INDEX_HTML
    assert "settingsThinkingTick" not in INDEX_HTML


def test_no_new_i18n_keys_were_added_for_sound():
    """The plan deliberately reuses the existing settings_label_sound /
    settings_desc_sound copy -- no new sound-specific i18n keys."""
    assert "sound_failure" not in MESSAGES_JS
    assert "sound_agent_spawned" not in MESSAGES_JS
    assert "sound_thinking_tick" not in MESSAGES_JS
