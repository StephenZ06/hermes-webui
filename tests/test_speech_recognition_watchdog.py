"""A started SpeechRecognition session that never produces a result must not
leave the mic silently dead.

Some Chromium forks (Arc, ungoogled builds, network-filtered setups) expose
``webkitSpeechRecognition`` but its backend never answers: recording starts,
the UI shows "listening", and no ``onresult`` / ``onerror`` / ``onend`` ever
fires. ``_armSrWatchdog`` in static/boot.js trips after a timeout with no
result and falls the mic over to server-side transcription.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOOT_JS = ROOT / "static" / "boot.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node not on PATH")

_DRIVER = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const input = JSON.parse(process.argv[3] || '{}');

function extractFunc(name) {
  const start = src.indexOf('function ' + name + '(');
  if (start < 0) throw new Error('missing ' + name);
  let i = src.indexOf('{', start), depth = 0;
  do { if (src[i] === '{') depth++; else if (src[i] === '}') depth--; i++; }
  while (depth > 0 && i < src.length);
  return src.slice(start, i);
}

const _store = {};
global.localStorage = {
  getItem: (k) => (k in _store ? _store[k] : null),
  setItem: (k, v) => { _store[k] = String(v); },
};
const toasts = [];
let _capturedTimer = null;
global.setTimeout = (fn) => { _capturedTimer = fn; return 1; };
global.clearTimeout = () => { _capturedTimer = null; };
global.window = { _micActive: true, _micPendingSend: true };

let _srWatchdog = null;
let _srSawResult = false;
const _srWatchdogMs = 8000;
const _canRecordAudio = !!input.canRecordAudio;
const _micForceMediaRecorderKey = 'mic_force_mediarecorder';
let _forceMediaRecorder = false;
let _isRecording = true;
let _micRestartCount = 3;
let _speechStopRequested = false;
let _activeCaptureMode = input.captureMode === undefined ? 'speech' : input.captureMode;
let _aborted = false;
let recognition = { abort() { _aborted = true; } };
function t(k) { return k; }
function showToast(m) { toasts.push(m); }
function _releaseMicWakeLock() { return Promise.resolve(); }
function _setRecording(on) { window._micActive = on; }

eval(extractFunc('_clearSrWatchdog'));
eval(extractFunc('_armSrWatchdog'));

_armSrWatchdog();
if (input.sawResult) _srSawResult = true;
if (input.fire && _capturedTimer) _capturedTimer();

process.stdout.write(JSON.stringify({
  forced: _store[_micForceMediaRecorderKey] || null,
  forceFlag: _forceMediaRecorder,
  recognitionNull: recognition === null,
  aborted: _aborted,
  micActive: !!window.window && window._micActive,
  pendingSend: window._micPendingSend,
  toasts,
}));
"""


@pytest.fixture(scope="module")
def driver(tmp_path_factory):
    p = tmp_path_factory.mktemp("sr_watchdog") / "d.js"
    p.write_text(_DRIVER, encoding="utf-8")
    return str(p)


def _run(driver, **payload):
    r = subprocess.run([NODE, driver, str(BOOT_JS), json.dumps(payload)],
                       capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    return json.loads(r.stdout)


def test_no_result_trips_the_fallback(driver):
    out = _run(driver, fire=True, canRecordAudio=True)
    assert out["forced"] == "1", "next click must use server transcription"
    assert out["forceFlag"] is True
    assert out["recognitionNull"] is True
    assert out["aborted"] is True
    assert out["micActive"] is False
    assert out["pendingSend"] is False
    assert out["toasts"] == ["mic_no_speech"]


def test_no_result_without_recorder_says_network(driver):
    out = _run(driver, fire=True, canRecordAudio=False)
    assert out["toasts"] == ["mic_network"]


def test_a_result_disarms_the_watchdog(driver):
    out = _run(driver, fire=True, sawResult=True, canRecordAudio=True)
    assert out["forced"] is None, "a live backend must never trip the fallback"
    assert out["toasts"] == []


def test_watchdog_ignores_a_session_that_already_moved_off_speech(driver):
    out = _run(driver, fire=True, captureMode="media", canRecordAudio=True)
    assert out["forced"] is None
    assert out["toasts"] == []
