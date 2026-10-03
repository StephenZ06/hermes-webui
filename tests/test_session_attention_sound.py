"""Regression tests for attention sounds on session attention state.

Approval/clarify prompts can surface through the sidebar session metadata rather
than the active live SSE stream. The sidebar badge path must play the distinct
attention sound when a session newly needs user input, without blasting sounds
for already-existing badges on initial load.
"""
import re
from pathlib import Path

REPO = Path(__file__).parent.parent
SESSIONS_JS = (REPO / "static" / "sessions.js").read_text(encoding="utf-8")
MESSAGES_JS = (REPO / "static" / "messages.js").read_text(encoding="utf-8")


def _body_from_brace(src: str, brace: int, label: str) -> str:
    assert brace >= 0, f"body opening brace not found for: {label}"
    depth = 1
    i = brace + 1
    while i < len(src) and depth:
        ch = src[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    assert depth == 0, f"body did not close for: {label}"
    return src[brace + 1 : i - 1]


def _function_body(src: str, name: str) -> str:
    marker = f"function {name}("
    start = src.find(marker)
    assert start >= 0, f"function not found: {name}"
    signature_end = src.find("){", start)
    assert signature_end >= 0, f"function body not found: {name}"
    return _body_from_brace(src, signature_end + 1, name)


def test_sidebar_attention_state_plays_distinct_sound_on_new_attention_only():
    sync_body = _function_body(SESSIONS_JS, "_syncSessionAttentionSoundState")
    apply_body = _function_body(SESSIONS_JS, "_applySessionListPayload")

    assert "let _sessionAttentionSoundPrimed = false;" in SESSIONS_JS
    assert "const _sessionAttentionSoundState = new Map();" in SESSIONS_JS
    assert "_syncSessionAttentionSoundState(_allSessions);" in apply_body
    assert "if(!_sessionAttentionSoundPrimed)" in sync_body
    assert "_sessionAttentionSoundPrimed=true;" in sync_body
    assert "playKey=typeof _attentionSoundKey==='function'?_attentionSoundKey(s.session_id,kind,count):`${s.session_id}:${sig}`;" in sync_body
    assert "if(playKey&&typeof playAttentionSound==='function') playAttentionSound(playKey);" in sync_body
    assert "playNotificationSound" not in sync_body


def test_attention_signature_tracks_kind_and_count_for_badge_changes():
    signature_body = _function_body(SESSIONS_JS, "_sessionAttentionSoundSignature")

    assert "attention.kind" in signature_body
    assert "Number.isFinite(count)" in signature_body
    assert "count<=0" in signature_body
    assert "approval" in signature_body
    assert "clarify" in signature_body
    assert "return `${kind}:${Math.max(1,count||1)}`;" in signature_body


_TONE_CALL = re.compile(r"_playTone\(\[([\d,\s]+)\],\s*([\d.]+),\s*'(\w+)',\s*([\d.]+)\)")


def _tone_args(body: str) -> dict:
    match = _TONE_CALL.search(body)
    assert match, "sound must be played through _playTone(freqs, duration, type, volume)"
    return {
        "freqs": [int(f) for f in match.group(1).split(",")],
        "duration": float(match.group(2)),
        "type": match.group(3),
        "volume": float(match.group(4)),
    }


def test_attention_sound_is_softer_short_reverse_of_completion_sound():
    attention_body = _function_body(MESSAGES_JS, "playAttentionSound")
    completion_body = _function_body(MESSAGES_JS, "playNotificationSound")

    assert "window._lastAttentionSoundAt" in attention_body
    assert "nowMs-window._lastAttentionSoundAt<900" in attention_body
    assert "window._attentionSoundSeenKeys" in attention_body
    assert "seen.has(dedupeKey)" in attention_body
    assert "seen.set(dedupeKey,nowMs)" in attention_body
    assert "300000" in attention_body

    # Both sounds are synthesized through the shared _playTone(freqs, duration,
    # type, volume) helper; compare their parameters.
    attention = _tone_args(attention_body)
    completion = _tone_args(completion_body)
    assert attention["type"] == completion["type"] == "sine"
    assert attention["freqs"] == list(reversed(completion["freqs"])), "attention is the reverse sweep"
    assert attention["freqs"][0] > attention["freqs"][-1], "attention sweeps down"
    assert attention["duration"] < completion["duration"], "attention is shorter"
    assert attention["volume"] < completion["volume"], "attention is softer"
