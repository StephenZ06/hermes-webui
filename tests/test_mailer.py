"""Hermes-wide mailer: one Gmail sender, a display name per feature."""

from __future__ import annotations

import os

import pytest

from api import mailer, profiles, shared_env


@pytest.fixture
def base(tmp_path, monkeypatch):
    work = tmp_path / "profiles" / "work"
    work.mkdir(parents=True)
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "secrets.env").write_text("")
    monkeypatch.setattr(profiles, "_resolve_base_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: False)
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: work)
    # The env writer also mirrors values into os.environ; never leak them.
    keys = ("HERMES_GMAIL_ADDRESS", "HERMES_GMAIL_APP_PASSWORD", "JOB_OS_GMAIL_ADDRESS", "JOB_OS_GMAIL_APP_PASSWORD")
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    yield tmp_path
    for key in keys:
        os.environ.pop(key, None)


def _capture():
    sent = []
    return sent, (lambda msg, a, p: sent.append({"from": msg["From"], "to": msg["To"], "subject": msg["Subject"]}))


@pytest.mark.parametrize("context,name", [("jobs", "Hermes Jobs"), ("business", "Hermes Business")])
def test_each_feature_sends_under_its_own_name(base, context, name):
    mailer.connect("bot@gmail.com", "abcdefghijklmnop", verify=lambda *_: None)
    sent, sender = _capture()
    mailer.send(context, "main@gmail.com", "Hello", "Body", sender=sender)
    assert sent == [{"from": f"{name} <bot@gmail.com>", "to": "main@gmail.com", "subject": "Hello"}]


def test_unknown_feature_is_refused_rather_than_mislabelled(base):
    mailer.connect("bot@gmail.com", "abcdefghijklmnop", verify=lambda *_: None)
    with pytest.raises(ValueError):
        mailer.send("marketing-spam", "main@gmail.com", "Hi", "Body", sender=lambda *_: None)


def test_connect_saves_neutral_keys_and_drops_legacy_ones(base):
    shared = base / "shared" / "secrets.env"
    shared.write_text("JOB_OS_GMAIL_ADDRESS=old@gmail.com\nJOB_OS_GMAIL_APP_PASSWORD=oldoldoldoldoldo\n")
    mailer.connect("bot@gmail.com", "abcdefghijklmnop", verify=lambda *_: None)
    stored = shared_env.parse_env_file(shared)
    assert stored["HERMES_GMAIL_ADDRESS"] == "bot@gmail.com"
    assert "JOB_OS_GMAIL_ADDRESS" not in stored and "JOB_OS_GMAIL_APP_PASSWORD" not in stored


def test_legacy_job_os_keys_still_work(base):
    (base / "shared" / "secrets.env").write_text("JOB_OS_GMAIL_ADDRESS=old@gmail.com\nJOB_OS_GMAIL_APP_PASSWORD=abcdefghijklmnop\n")
    assert mailer.status()["address"] is True
    sent, sender = _capture()
    mailer.send("business", "main@gmail.com", "Hi", "Body", sender=sender)
    assert sent[0]["from"] == "Hermes Business <old@gmail.com>"


def test_test_email_names_the_feature(base):
    mailer.connect("bot@gmail.com", "abcdefghijklmnop", verify=lambda *_: None)
    sent, sender = _capture()
    mailer.send_test("business", "main@gmail.com", sender=sender)
    assert sent == [{"from": "Hermes Business <bot@gmail.com>", "to": "main@gmail.com", "subject": "Hermes Business: test email"}]


def test_disconnect_removes_new_and_legacy_keys(base):
    shared = base / "shared" / "secrets.env"
    shared.write_text("JOB_OS_GMAIL_ADDRESS=old@gmail.com\n")
    mailer.connect("bot@gmail.com", "abcdefghijklmnop", verify=lambda *_: None)
    mailer.disconnect()
    assert not {k for k in shared_env.parse_env_file(shared) if "GMAIL" in k}


def test_mail_carries_its_own_date_and_message_id(base):
    mailer.connect("bot@gmail.com", "abcdefghijklmnop", verify=lambda *_: None)
    seen = []
    mailer.send("jobs", "main@gmail.com", "Hi", "Body", sender=lambda msg, a, p: seen.append((msg["Date"], msg["Message-ID"])))
    date, message_id = seen[0]
    assert date and message_id and message_id.endswith("@gmail.com>")


def test_mail_includes_a_professional_html_alternative_without_changing_plain_text(base):
    mailer.connect("bot@gmail.com", "abcdefghijklmnop", verify=lambda *_: None)
    seen = []
    mailer.send(
        "business", "main@gmail.com", "Daily <brief>", "First line\nSecond <line>",
        sender=lambda msg, _address, _password: seen.append(msg),
    )

    message = seen[0]
    plain, html = message.get_body(preferencelist=("plain", "html")), message.get_body(preferencelist=("html",))
    assert plain.get_content().strip() == "First line\nSecond <line>"
    rendered = html.get_content()
    assert "Hermes Business" in rendered
    assert "Daily &lt;brief&gt;" in rendered
    assert "Second &lt;line&gt;" in rendered
    assert "<table" in rendered
