"""Library catalog: one folder per library under HERMES_HOME/libraries, one
file per component, with fixed style / motion / role / platform tags."""

import pytest

from api import library_catalog as lc


LIB = """---
name: Rare UI
source: https://github.com/swamimalode07/rare-ui
license: MIT
kind: copy-paste
frameworks: [react]
tailwind: true
install: ""
---
Notes about the library.
"""

SOFT = """---
name: Soft fade text
role: text-effect
style: [minimal, elegant]
motion: subtle
platform: [web]
demo: https://example.com/soft
files: [src/soft.tsx]
---
"""


def _write_lib(root, slug="rare-ui", lib=LIB, comps=(("soft-fade", SOFT),)):
    d = root / slug
    (d / "components").mkdir(parents=True)
    (d / "LIBRARY.md").write_text(lib)
    for name, text in comps:
        (d / "components" / f"{name}.md").write_text(text)
    return d


def test_front_matter_is_split_from_the_body():
    meta, body = lc.parse_front_matter(LIB)
    assert meta["name"] == "Rare UI" and meta["frameworks"] == ["react"]
    assert body.strip() == "Notes about the library."
    assert lc.parse_front_matter("no front matter") == ({}, "no front matter")


def test_a_complete_library_and_component_need_no_details(tmp_path):
    _write_lib(tmp_path)
    [lib] = lc.list_libraries(tmp_path)
    assert lib["slug"] == "rare-ui" and lib["kind"] == "copy-paste" and lib["needs_details"] is False
    [comp] = lib["components"]
    assert comp["slug"] == "soft-fade" and comp["style"] == ["minimal", "elegant"]
    assert comp["motion"] == "subtle" and comp["needs_details"] is False
    assert comp["preview"] is None


def test_unknown_tags_are_dropped_and_mark_the_entry_as_needing_details(tmp_path):
    bad = SOFT.replace("[minimal, elegant]", "[shiny]").replace("subtle", "wild")
    _write_lib(tmp_path, comps=(("soft-fade", bad),))
    [comp] = lc.list_libraries(tmp_path)[0]["components"]
    assert comp["style"] == [] and comp["motion"] == "" and comp["needs_details"] is True


def test_malformed_front_matter_lists_with_needs_details_instead_of_crashing(tmp_path):
    _write_lib(tmp_path, lib="---\nname: [unclosed\n---\n")
    [lib] = lc.list_libraries(tmp_path)
    assert lib["needs_details"] is True and lib["name"] == "rare-ui"


def test_preview_files_are_reported_when_present(tmp_path):
    d = _write_lib(tmp_path)
    (d / "previews").mkdir()
    (d / "previews" / "soft-fade.webp").write_bytes(b"RIFF")
    (d / "previews" / "soft-fade.loop.webp").write_bytes(b"RIFF")
    [comp] = lc.list_libraries(tmp_path)[0]["components"]
    assert comp["preview"] == "rare-ui/previews/soft-fade.webp"
    assert comp["loop"] == "rare-ui/previews/soft-fade.loop.webp"


def test_save_writes_a_library_that_lists_back_the_same(tmp_path):
    lc.save_library(tmp_path, "my-lib", {"name": "My lib", "source": "https://x.dev", "kind": "link",
                                         "frameworks": ["vanilla"], "tailwind": False, "license": "", "install": ""},
                    [{"name": "Glow card", "role": "cards", "style": ["bold"], "motion": "expressive", "platform": ["web"]}])
    [lib] = lc.list_libraries(tmp_path)
    assert lib["name"] == "My lib" and lib["components"][0]["slug"] == "glow-card"
    assert lib["components"][0]["role"] == "cards"


def test_update_component_changes_only_the_given_tags(tmp_path):
    _write_lib(tmp_path)
    out = lc.update_component(tmp_path, "rare-ui", "soft-fade", {"style": ["playful"], "motion": "expressive"})
    assert out["style"] == ["playful"] and out["motion"] == "expressive" and out["role"] == "text-effect"
    assert lc.list_libraries(tmp_path)[0]["components"][0]["style"] == ["playful"]


@pytest.mark.parametrize("parts", [("..", "x"), ("a/../../b",), ("/etc",), ("",)])
def test_paths_outside_the_catalog_are_refused(tmp_path, parts):
    with pytest.raises(ValueError):
        lc.safe_child(tmp_path, *parts)


def test_slugs_are_lowercase_dashed_and_checked():
    assert lc.slugify("  Rare UI! ") == "rare-ui"
    for bad in ("", "...", "-" * 3):
        with pytest.raises(ValueError):
            lc.slugify(bad)
