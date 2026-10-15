"""Phone framing and gestures of the Office scene (static/office/scene.js).

The scene needs WebGL, so these run the framing arithmetic under node and check the gesture code's
structure: the camera itself cannot be driven here.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCENE = (Path(__file__).resolve().parent.parent / "static" / "office" / "scene.js").read_text(encoding="utf-8")


def _zoom_for(width, height, radius, boost=None):
    node = shutil.which("node")
    if not node:
        pytest.skip("needs node")
    const = lambda name: re.search(rf"const {name} = ([^;]+);", SCENE).group(1)
    start = SCENE.index("  function zoomForRadius(")
    end = SCENE.index("\n  // ---- camera motion", start)
    program = f"""
      const FRUSTUM_HALF_HEIGHT = {const('FRUSTUM_HALF_HEIGHT')};
      const FRAME_HEADROOM = {const('FRAME_HEADROOM')};
      const PHONE_FRAME_BOOST = {const('PHONE_FRAME_BOOST') if boost is None else boost};
      const ISO_VERTICAL_SCALE = 0.92 / Math.hypot(1, 0.92, 1);
      {SCENE[start:end]}
      console.log(JSON.stringify(zoomForRadius({width}, {height}, {radius})));
    """
    return json.loads(subprocess.run([node, "-e", program], capture_output=True, text=True, check=True).stdout)


def test_a_phone_sized_stage_frames_the_office_closer():
    boost = float(re.search(r"const PHONE_FRAME_BOOST = ([\d.]+);", SCENE).group(1))
    assert 1.1 < boost <= 1.3                                                      # a nudge, not a different view
    for width, height in ((430, 760), (390, 844), (430, 932)):                     # phones, portrait
        assert _zoom_for(width, height, 60) == pytest.approx(_zoom_for(width, height, 60, boost=1) * boost)


def test_the_boost_does_not_touch_wider_stages():
    for width, height in ((430, 420), (700, 900), (1400, 900)):                    # square-ish, a tablet, a desktop panel
        assert _zoom_for(width, height, 60) == pytest.approx(_zoom_for(width, height, 60, boost=1))


def test_a_pinch_is_never_read_as_a_tap_on_empty_ground():
    # The last finger lifting after a quick pinch used to count as a tap and pulled the camera back out.
    assert "let multiTouch = false;" in SCENE
    down = SCENE[SCENE.index("function onPointerDown("):SCENE.index("let hoverAt = null;")]
    assert "multiTouch = false;" in down and "multiTouch = true;" in down
    assert down.index("multiTouch = true;") > down.index("gesture = 'pinch';")
    end = SCENE[SCENE.index("function endPointer("):SCENE.index("function handleTap(")]
    assert "wasSingle && !multiTouch && gesture == null" in end
    assert end.index("multiTouch = false;") > end.index("handleTap(downClient.x, downClient.y);")   # cleared only once every finger is up


def test_a_touch_screen_renders_at_a_higher_resolution_that_the_governor_may_not_drop_below_1_5x():
    assert "window.matchMedia('(pointer: coarse)').matches" in SCENE
    assert "touchScreen ? 2.5 : 2" in SCENE
    assert "min: touchScreen ? Math.min(preferredPixelRatio, 1.5) : 1" in SCENE
