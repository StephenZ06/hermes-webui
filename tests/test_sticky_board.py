"""Multi-board Sticky Board storage + project-folder linkage
(api/sticky_board.py).

Boards are shared across every hermes-agent profile (STATE_DIR is not
profile-scoped) and can optionally link to a WebUI Project folder
(api/models.py's load_projects()/PROJECTS_FILE). When a linked project has
a bound workspace_path, the board's content is mirrored into a clearly
delimited section of that workspace's AGENTS.md -- a real, already-proven
ingestion path (api/routes.py's _project_context_candidates() confirms
AGENTS.md at a project's workspace root is the first file hermes-agent
looks for).
"""
import pathlib

from api import sticky_board


def _project(project_id, workspace_path=None):
    return {"project_id": project_id, "name": "Proj", "workspace_path": workspace_path}


class TestBoardCRUD:
    def test_load_boards_missing_file_answers_empty_list(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sticky_board, "BOARDS_FILE", tmp_path / "sticky_boards.json")
        monkeypatch.setattr(sticky_board, "_LEGACY_BOARD_FILE", tmp_path / "sticky_board.json")
        assert sticky_board.load_boards() == []

    def test_load_boards_corrupt_file_answers_empty_list(self, tmp_path, monkeypatch):
        f = tmp_path / "sticky_boards.json"
        f.write_text("not json", encoding="utf-8")
        monkeypatch.setattr(sticky_board, "BOARDS_FILE", f)
        assert sticky_board.load_boards() == []

    def test_migrates_legacy_single_board_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sticky_board, "BOARDS_FILE", tmp_path / "sticky_boards.json")
        legacy = tmp_path / "sticky_board.json"
        legacy.write_text('{"columns": [{"id": "c1", "title": "To Do", "notes": []}]}', encoding="utf-8")
        monkeypatch.setattr(sticky_board, "_LEGACY_BOARD_FILE", legacy)
        boards = sticky_board.load_boards()
        assert len(boards) == 1
        assert boards[0]["name"] == "My Board"
        assert boards[0]["project_id"] is None
        assert boards[0]["columns"][0]["title"] == "To Do"
        # Migration persists -- a second call doesn't re-migrate/duplicate.
        assert sticky_board.load_boards() == boards

    def test_create_rename_delete_round_trip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sticky_board, "BOARDS_FILE", tmp_path / "sticky_boards.json")
        board = sticky_board.create_board("Sprint 1")
        assert board["name"] == "Sprint 1"
        assert board["project_id"] is None
        assert sticky_board.get_board(board["id"])["name"] == "Sprint 1"

        renamed = sticky_board.rename_board(board["id"], "Sprint 2")
        assert renamed["name"] == "Sprint 2"

        assert sticky_board.delete_board(board["id"]) is True
        assert sticky_board.get_board(board["id"]) is None
        assert sticky_board.delete_board(board["id"]) is False

    def test_save_board_columns(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sticky_board, "BOARDS_FILE", tmp_path / "sticky_boards.json")
        board = sticky_board.create_board("B")
        cols = [{"id": "c1", "title": "Done", "notes": []}]
        updated = sticky_board.save_board_columns(board["id"], cols)
        assert updated["columns"] == cols
        assert sticky_board.get_board(board["id"])["columns"] == cols

    def test_multiple_boards_coexist(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sticky_board, "BOARDS_FILE", tmp_path / "sticky_boards.json")
        a = sticky_board.create_board("A")
        b = sticky_board.create_board("B")
        assert {x["id"] for x in sticky_board.load_boards()} == {a["id"], b["id"]}


class TestAgentsMdSync:
    def _wire(self, tmp_path, monkeypatch, *, workspace_path=None, project_id="proj-1"):
        monkeypatch.setattr(sticky_board, "BOARDS_FILE", tmp_path / "sticky_boards.json")
        ws = workspace_path
        if ws is None:
            ws = tmp_path / "workspace"
            ws.mkdir()
        monkeypatch.setattr("api.models.load_projects", lambda: [_project(project_id, str(ws))])
        monkeypatch.setattr("api.workspace.resolve_trusted_workspace", lambda p: pathlib.Path(p))
        monkeypatch.setattr("api.workspace.is_blocked_system_path", lambda p: False)
        return ws

    def test_unlinked_board_writes_nothing(self, tmp_path, monkeypatch):
        self._wire(tmp_path, monkeypatch)
        board = sticky_board.create_board("No project")
        sticky_board.save_board_columns(board["id"], [{"id": "c1", "title": "X", "notes": []}])
        assert not (tmp_path / "workspace" / "AGENTS.md").exists()

    def test_project_without_workspace_path_writes_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sticky_board, "BOARDS_FILE", tmp_path / "sticky_boards.json")
        monkeypatch.setattr("api.models.load_projects", lambda: [_project("proj-1", None)])
        board = sticky_board.create_board("Linked", project_id="proj-1")
        sticky_board.save_board_columns(board["id"], [])
        # Nothing to assert a path for -- just confirm it didn't blow up and
        # no stray file appeared anywhere under tmp_path.
        assert list(tmp_path.rglob("AGENTS.md")) == []

    def test_linked_board_creates_agents_md_with_delimited_section(self, tmp_path, monkeypatch):
        ws = self._wire(tmp_path, monkeypatch)
        board = sticky_board.create_board("Sprint", project_id="proj-1")
        board = sticky_board.save_board_columns(board["id"], [
            {"id": "c1", "title": "To Do", "notes": [
                {"id": "n1", "title": "Ship it", "subItems": ["write tests", "deploy"]},
            ]},
        ])
        agents_md = ws / "AGENTS.md"
        assert agents_md.exists()
        content = agents_md.read_text(encoding="utf-8")
        assert "Sticky Notes -- Sprint" in content
        assert "To Do" in content
        assert "Ship it" in content
        assert "write tests" in content
        assert f"sticky-board:{board['id']} start" in content
        assert f"sticky-board:{board['id']} end" in content

    def test_resaving_updates_section_in_place_not_duplicated(self, tmp_path, monkeypatch):
        ws = self._wire(tmp_path, monkeypatch)
        board = sticky_board.create_board("Sprint", project_id="proj-1")
        sticky_board.save_board_columns(board["id"], [{"id": "c1", "title": "V1", "notes": []}])
        sticky_board.save_board_columns(board["id"], [{"id": "c1", "title": "V2", "notes": []}])
        content = (ws / "AGENTS.md").read_text(encoding="utf-8")
        assert content.count(f"sticky-board:{board['id']} start") == 1
        assert "V2" in content
        assert "V1" not in content

    def test_preserves_existing_agents_md_content(self, tmp_path, monkeypatch):
        ws = self._wire(tmp_path, monkeypatch)
        (ws / "AGENTS.md").write_text("# My hand-written project notes\n\nDo not touch.\n", encoding="utf-8")
        board = sticky_board.create_board("Sprint", project_id="proj-1")
        sticky_board.save_board_columns(board["id"], [{"id": "c1", "title": "X", "notes": []}])
        content = (ws / "AGENTS.md").read_text(encoding="utf-8")
        assert "My hand-written project notes" in content
        assert "Do not touch." in content
        assert "Sticky Notes -- Sprint" in content

    def test_deleting_board_removes_its_section_only(self, tmp_path, monkeypatch):
        ws = self._wire(tmp_path, monkeypatch)
        keep_text = "# Keep me\n"
        (ws / "AGENTS.md").write_text(keep_text, encoding="utf-8")
        board = sticky_board.create_board("Sprint", project_id="proj-1")
        sticky_board.save_board_columns(board["id"], [{"id": "c1", "title": "X", "notes": []}])
        sticky_board.delete_board(board["id"])
        content = (ws / "AGENTS.md").read_text(encoding="utf-8")
        assert "Keep me" in content
        assert "Sticky Notes" not in content

    def test_two_boards_linked_to_same_project_get_separate_sections(self, tmp_path, monkeypatch):
        ws = self._wire(tmp_path, monkeypatch)
        a = sticky_board.create_board("Board A", project_id="proj-1")
        b = sticky_board.create_board("Board B", project_id="proj-1")
        sticky_board.save_board_columns(a["id"], [{"id": "c1", "title": "A-col", "notes": []}])
        sticky_board.save_board_columns(b["id"], [{"id": "c1", "title": "B-col", "notes": []}])
        content = (ws / "AGENTS.md").read_text(encoding="utf-8")
        assert "Board A" in content and "A-col" in content
        assert "Board B" in content and "B-col" in content
        sticky_board.delete_board(a["id"])
        content = (ws / "AGENTS.md").read_text(encoding="utf-8")
        assert "Board A" not in content
        assert "Board B" in content and "B-col" in content

    def test_reassigning_project_moves_section_between_workspaces(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sticky_board, "BOARDS_FILE", tmp_path / "sticky_boards.json")
        ws1 = tmp_path / "ws1"; ws1.mkdir()
        ws2 = tmp_path / "ws2"; ws2.mkdir()
        projects = {"p1": _project("p1", str(ws1)), "p2": _project("p2", str(ws2))}
        monkeypatch.setattr("api.models.load_projects", lambda: list(projects.values()))
        monkeypatch.setattr("api.workspace.resolve_trusted_workspace", lambda p: pathlib.Path(p))
        monkeypatch.setattr("api.workspace.is_blocked_system_path", lambda p: False)

        board = sticky_board.create_board("Roaming", project_id="p1")
        sticky_board.save_board_columns(board["id"], [{"id": "c1", "title": "X", "notes": []}])
        assert "Roaming" in (ws1 / "AGENTS.md").read_text(encoding="utf-8")

        sticky_board.set_board_project(board["id"], "p2")
        assert not (ws1 / "AGENTS.md").exists() or "Roaming" not in (ws1 / "AGENTS.md").read_text(encoding="utf-8")
        assert "Roaming" in (ws2 / "AGENTS.md").read_text(encoding="utf-8")

    def test_blocked_workspace_path_is_never_written(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sticky_board, "BOARDS_FILE", tmp_path / "sticky_boards.json")
        ws = tmp_path / "workspace"; ws.mkdir()
        monkeypatch.setattr("api.models.load_projects", lambda: [_project("proj-1", str(ws))])
        monkeypatch.setattr("api.workspace.resolve_trusted_workspace", lambda p: pathlib.Path(p))
        monkeypatch.setattr("api.workspace.is_blocked_system_path", lambda p: True)  # simulate a rejected path
        board = sticky_board.create_board("Sprint", project_id="proj-1")
        sticky_board.save_board_columns(board["id"], [{"id": "c1", "title": "X", "notes": []}])
        assert not (ws / "AGENTS.md").exists()


class TestRoutesWiring:
    def _routes_src(self):
        return pathlib.Path("api/routes.py").read_text(encoding="utf-8")

    def test_all_endpoints_are_wired(self):
        src = self._routes_src()
        for path, fn in [
            ('"/api/sticky_boards"', "from api.sticky_board import load_boards"),
            ('"/api/sticky_boards/create"', "from api.sticky_board import create_board"),
            ('"/api/sticky_boards/rename"', "from api.sticky_board import rename_board"),
            ('"/api/sticky_boards/delete"', "from api.sticky_board import delete_board"),
            ('"/api/sticky_boards/set_project"', "from api.sticky_board import set_board_project"),
            ('"/api/sticky_boards/save"', "from api.sticky_board import save_board_columns"),
        ]:
            assert path in src, f"missing route {path}"
            assert fn in src, f"missing import for {path}"
