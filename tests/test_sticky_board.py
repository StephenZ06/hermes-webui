"""Server-side storage for the Sticky Board (api/sticky_board.py).

The vendored board (static/vendor/sticky-board/, see PROVENANCE.md there)
originally persisted to the browser's own localStorage -- per-browser, not
shared across devices. This backs it with a flat JSON document at
STATE_DIR/sticky_board.json instead, mirroring api/models.py's
load_projects()/PROJECTS_FILE load/save-whole convention.
"""
import pathlib

from api import sticky_board


def test_load_board_missing_file_answers_none(tmp_path, monkeypatch):
    monkeypatch.setattr(sticky_board, "BOARD_FILE", tmp_path / "sticky_board.json")
    assert sticky_board.load_board() is None


def test_load_board_corrupt_file_answers_none(tmp_path, monkeypatch):
    f = tmp_path / "sticky_board.json"
    f.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(sticky_board, "BOARD_FILE", f)
    assert sticky_board.load_board() is None


def test_load_board_non_dict_json_answers_none(tmp_path, monkeypatch):
    f = tmp_path / "sticky_board.json"
    f.write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setattr(sticky_board, "BOARD_FILE", f)
    assert sticky_board.load_board() is None


def test_save_then_load_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(sticky_board, "BOARD_FILE", tmp_path / "sticky_board.json")
    board = {"columns": [{"id": "c1", "title": "To Do", "color": "#fff59d", "notes": [
        {"id": "n1", "title": "Test note", "color": "#fff59d", "subItems": ["a", "b"], "assignee": "Zola"},
    ]}]}
    sticky_board.save_board(board)
    assert sticky_board.load_board() == board


def test_save_overwrites_previous_board(tmp_path, monkeypatch):
    monkeypatch.setattr(sticky_board, "BOARD_FILE", tmp_path / "sticky_board.json")
    sticky_board.save_board({"columns": [{"id": "c1", "title": "old", "color": None, "notes": []}]})
    sticky_board.save_board({"columns": [{"id": "c2", "title": "new", "color": None, "notes": []}]})
    loaded = sticky_board.load_board()
    assert len(loaded["columns"]) == 1
    assert loaded["columns"][0]["title"] == "new"


class TestRoutesWiring:
    """Source-pinned: api/routes.py's GET/POST /api/sticky_board handlers,
    mirroring tests/test_opencode_go_usage_widget.py's approach for routes
    that need a live server to exercise end-to-end."""

    def _routes_src(self):
        return pathlib.Path("api/routes.py").read_text(encoding="utf-8")

    def test_get_endpoint_is_wired(self):
        src = self._routes_src()
        assert '"/api/sticky_board"' in src
        assert "from api.sticky_board import load_board" in src

    def test_post_endpoint_is_wired(self):
        src = self._routes_src()
        assert "from api.sticky_board import save_board" in src
        assert 'require(body, "board")' in src
