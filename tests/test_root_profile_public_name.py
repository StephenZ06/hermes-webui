"""A renamed root profile is reported to the browser by its display name.

With no sticky ``active_profile`` the server's internal active name is the
legacy alias ``default``. The profile list already names the root row by its
``profile.yaml`` ``display_name`` (``conductor``), so a hard reset used to show
a ``default`` profile that the switcher did not list. Every response that tells
the browser which profile is active now uses the same public name.
"""

import api.profiles as p


def _rename_root(monkeypatch, tmp_path, display_name):
    (tmp_path / 'profile.yaml').write_text(f'display_name: {display_name}\n', encoding='utf-8')
    monkeypatch.setattr(p, '_DEFAULT_HERMES_HOME', tmp_path)
    monkeypatch.setattr(p, '_is_isolated_profile_mode', lambda: False)


def test_root_alias_is_reported_by_its_display_name(monkeypatch, tmp_path):
    _rename_root(monkeypatch, tmp_path, 'conductor')
    assert p.public_profile_name('default') == 'conductor'
    assert p.public_profile_name('') == 'conductor'


def test_named_profiles_and_unrenamed_root_keep_their_names(monkeypatch, tmp_path):
    _rename_root(monkeypatch, tmp_path, 'conductor')
    assert p.public_profile_name('architecture') == 'architecture'
    (tmp_path / 'profile.yaml').write_text('description: no display name\n', encoding='utf-8')
    assert p.public_profile_name('default') == 'default'


def test_profile_active_route_reports_the_display_name(monkeypatch, tmp_path):
    import api.routes as routes
    _rename_root(monkeypatch, tmp_path, 'conductor')
    monkeypatch.setattr(p, 'get_active_profile_name', lambda: 'default')
    monkeypatch.setattr(p, 'get_active_hermes_home', lambda: tmp_path)
    monkeypatch.setattr(routes, 'get_profile_default_workspace', lambda: None)
    sent = {}
    monkeypatch.setattr(routes, 'j', lambda handler, payload, **kw: sent.update(payload))
    routes._route_get_api_profile_active(None, None)
    assert sent['name'] == 'conductor'
    assert sent['is_default'] is True
