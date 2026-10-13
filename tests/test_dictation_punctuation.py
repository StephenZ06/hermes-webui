"""Dictated text is punctuated before it reaches the composer.

Groq Whisper drops punctuation on short dictations and the browser's own
speech recognition never adds any, so static/punctuate.js tidies every
dictated piece: spoken punctuation becomes symbols, sentences and "I" are
capitalised, and a missing end mark is added ("?" for a question).
"""
import json
import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).parent.parent
PUNCT = REPO / "static" / "punctuate.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is required")

CASES = [
    # (dictated, text already in the composer, expected)
    ("hello how are you doing today", "", "Hello how are you doing today?"),
    ("send the report to sam", "", "Send the report to sam."),
    ("i think i'm done full stop thanks", "", "I think I'm done. Thanks."),
    ("first item comma second item new line third", "", "First item, second item\nThird."),
    ("can you check this question mark", "", "Can you check this?"),
    ("Already punctuated, fine.", "", "Already punctuated, fine."),
    ("and then more words", "Draft so far", "and then more words."),
    ("next sentence here", "Done. ", "Next sentence here."),
    ("is it ready", "Hmm, ", "is it ready?"),
    ("", "", ""),
]

_DRIVER = r"""
const mod = await import(process.argv[2]);
const punctuate = mod.punctuateDictation || (mod.default && mod.default.punctuateDictation);
const cases = JSON.parse(process.argv[3]);
console.log(JSON.stringify(cases.map(([text, before]) => punctuate(text, before))));
"""


def test_dictation_is_punctuated(tmp_path):
    driver = tmp_path / "drive.mjs"
    driver.write_text(_DRIVER, encoding="utf-8")
    out = subprocess.run([NODE, str(driver), PUNCT.as_uri(), json.dumps([[c[0], c[1]] for c in CASES])],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout.strip().splitlines()[-1])
    assert got == [c[2] for c in CASES]


def test_both_dictation_paths_use_it():
    boot = (REPO / "static" / "boot.js").read_text(encoding="utf-8")
    index = (REPO / "static" / "index.html").read_text(encoding="utf-8")
    assert 'src="static/punctuate.js' in index
    assert boot.count("_punctuateDictation(") >= 3, "server STT, browser STT and voice mode must all punctuate"
