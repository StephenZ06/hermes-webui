"""Coverage for the workspace_hidden_folders picker filter.

A workspace root is often shared with directories nobody ever binds a project
to -- tooling checkouts, vendored skill bundles, caches. This setting keeps
those out of the folder pickers by name or glob. It is a display filter only:
nothing is hidden on disk, and the file tree and every path-resolution guard
are untouched, so a hidden folder is still perfectly reachable by typing its
path.
"""
import pathlib

import api.config as config
import api.workspace as workspace


REPO_ROOT = pathlib.Path(__file__).parent.parent
INDEX_HTML = (REPO_ROOT / "static" / "index.html").read_text(encoding="utf-8")
PANELS_JS = (REPO_ROOT / "static" / "panels.js").read_text(encoding="utf-8")
I18N_JS = (REPO_ROOT / "static" / "i18n.js").read_text(encoding="utf-8")


class TestMatching:
    def test_no_patterns_hides_nothing(self):
        assert workspace._is_hidden_workspace_folder("ecc", []) is False

    def test_exact_name_matches(self):
        assert workspace._is_hidden_workspace_folder("ecc", ["ecc"]) is True

    def test_matching_is_case_insensitive(self):
        assert workspace._is_hidden_workspace_folder("ECC", ["ecc"]) is True
        assert workspace._is_hidden_workspace_folder("ecc", ["ECC"]) is True

    def test_glob_matches_a_family_of_folders(self):
        patterns = ["ecc", "ecc-*"]
        assert workspace._is_hidden_workspace_folder("ecc-minimal-skills", patterns) is True
        assert workspace._is_hidden_workspace_folder("ecc-profiles-skills", patterns) is True

    def test_unrelated_folders_are_untouched(self):
        patterns = ["ecc", "ecc-*"]
        for name in ("MiniPC-Main", "remote", "Business", "eccentric-notes"):
            assert workspace._is_hidden_workspace_folder(name, patterns) is False, name

    def test_a_bare_name_does_not_match_by_prefix(self):
        # "ecc" must not swallow "eccentric" -- only an explicit glob does that.
        assert workspace._is_hidden_workspace_folder("eccentric", ["ecc"]) is False


class TestSuggestionsFilter:
    def _tree(self, tmp_path):
        for name in ("MiniPC-Main", "remote", "ecc", "ecc-minimal-skills", "keep"):
            (tmp_path / name).mkdir()
        return tmp_path

    @staticmethod
    def _children(root, suggestions):
        # list_workspace_suggestions() also echoes the trusted root that
        # prefix-matches, so keep only what is strictly inside the directory.
        base = str(root).rstrip("/") + "/"
        return sorted(
            pathlib.Path(p).name for p in suggestions if str(p).startswith(base)
        )

    def test_hidden_folders_are_dropped_from_suggestions(self, tmp_path, monkeypatch):
        root = self._tree(tmp_path)
        monkeypatch.setattr(workspace, "_trusted_workspace_roots", lambda: [root])
        monkeypatch.setattr(
            workspace, "hidden_workspace_folder_patterns", lambda: ["ecc", "ecc-*"]
        )
        names = self._children(root, workspace.list_workspace_suggestions(str(root) + "/"))
        assert names == ["MiniPC-Main", "keep", "remote"]

    def test_without_the_setting_everything_is_listed(self, tmp_path, monkeypatch):
        root = self._tree(tmp_path)
        monkeypatch.setattr(workspace, "_trusted_workspace_roots", lambda: [root])
        monkeypatch.setattr(workspace, "hidden_workspace_folder_patterns", lambda: [])
        names = self._children(root, workspace.list_workspace_suggestions(str(root) + "/"))
        assert names == [
            "MiniPC-Main",
            "ecc",
            "ecc-minimal-skills",
            "keep",
            "remote",
        ]

    def test_a_hidden_folder_is_still_reachable_by_typing_its_path(self, tmp_path, monkeypatch):
        # The filter is cosmetic: it must not become a path-authorization rule,
        # or someone would be locked out of a folder they deliberately named.
        root = self._tree(tmp_path)
        (root / "ecc" / "inner").mkdir()
        monkeypatch.setattr(workspace, "_trusted_workspace_roots", lambda: [root])
        monkeypatch.setattr(
            workspace, "hidden_workspace_folder_patterns", lambda: ["ecc", "ecc-*"]
        )
        names = self._children(
            root / "ecc", workspace.list_workspace_suggestions(str(root / "ecc") + "/")
        )
        assert names == ["inner"]


class TestSettingPlumbing:
    def test_default_is_empty_and_the_key_is_writable(self):
        assert config._SETTINGS_DEFAULTS["workspace_hidden_folders"] == []
        assert "workspace_hidden_folders" in config._SETTINGS_ALLOWED_KEYS

    def test_patterns_reader_tolerates_a_broken_setting(self, monkeypatch):
        monkeypatch.setattr(config, "load_settings", lambda: {"workspace_hidden_folders": "ecc"})
        assert workspace.hidden_workspace_folder_patterns() == []

    def test_patterns_reader_drops_blank_and_non_string_entries(self, monkeypatch):
        monkeypatch.setattr(
            config,
            "load_settings",
            lambda: {"workspace_hidden_folders": ["ecc", "  ", 7, " ecc-* "]},
        )
        assert workspace.hidden_workspace_folder_patterns() == ["ecc", "ecc-*"]


class TestSettingsUi:
    def test_field_and_i18n_keys_exist(self):
        assert 'id="settingsHiddenFolders"' in INDEX_HTML
        assert 'data-i18n="settings_label_hidden_folders"' in INDEX_HTML
        assert I18N_JS.count("settings_label_hidden_folders:") == 15
        assert I18N_JS.count("settings_desc_hidden_folders:") == 15

    def test_input_is_parsed_into_the_settings_payload(self):
        assert "function _parseHiddenFoldersInput" in PANELS_JS
        assert "payload.workspace_hidden_folders=_parseHiddenFoldersInput" in PANELS_JS

    def test_path_separators_are_rejected_client_side_too(self):
        parser = PANELS_JS[PANELS_JS.index("function _parseHiddenFoldersInput"):]
        parser = parser[: parser.index("\n}")]
        assert "indexOf('/')<0" in parser
