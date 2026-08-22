from api.workspace import _clean_workspace_list


def test_legacy_entries_still_clean_as_local(tmp_path):
    legacy = [{"path": str(tmp_path), "name": "Home"}]

    cleaned = _clean_workspace_list(legacy)

    assert len(cleaned) == 1
    assert cleaned[0]["name"] == "Home"
    assert "kind" not in cleaned[0]
    assert "remote" not in cleaned[0]


def test_remote_entry_survives_cleaning(tmp_path):
    remote_path = tmp_path / "remote" / "pi5"  # need not exist yet — never mounted
    entries = [{
        "path": str(remote_path),
        "name": "Raspberry Pi 5",
        "kind": "remote",
        "remote": {"host": "pi@192.168.1.50", "remote_path": "/home/pi/projects", "key_path": "/keys/id_rsa"},
    }]

    cleaned = _clean_workspace_list(entries)

    assert len(cleaned) == 1
    assert cleaned[0]["kind"] == "remote"
    assert cleaned[0]["remote"] == {
        "host": "pi@192.168.1.50",
        "remote_path": "/home/pi/projects",
        "key_path": "/keys/id_rsa",
    }


def test_remote_entry_with_malformed_remote_field_degrades_to_local(tmp_path):
    entries = [{"path": str(tmp_path), "name": "Broken", "kind": "remote", "remote": "not-a-dict"}]

    cleaned = _clean_workspace_list(entries)

    assert len(cleaned) == 1
    assert "kind" not in cleaned[0]
