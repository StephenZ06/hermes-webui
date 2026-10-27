"""Hermes-wide Gmail sender.

One Gmail account (a dedicated one works best) sends email for every Hermes
feature; each feature sends under its own display name -- "Hermes Jobs",
"Hermes Business" -- so the inbox shows which part of Hermes wrote. The
recipient is chosen by the feature (e.g. Jobs -> Notifications -> Send to).

The address and app password are verified with a real login (SMTP for
sending, IMAP for reading replies) *before* they are saved, then written with
:func:`api.shared_env.write_env_values` -- to the shared secrets file every
profile reads, when that layer is enabled. The password is never returned to
the browser or logged; status is reported as booleans.
"""

from __future__ import annotations

import html
import imaplib
import os
import re
import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path
from typing import Callable

# Feature-neutral names first; the Job OS names are read for older installs.
ADDRESS_KEYS = ("HERMES_GMAIL_ADDRESS", "JOB_OS_GMAIL_ADDRESS")
PASSWORD_KEYS = ("HERMES_GMAIL_APP_PASSWORD", "JOB_OS_GMAIL_APP_PASSWORD")
# The display name each feature sends under.
SENDER_NAMES = {
    "jobs": "Hermes Jobs",
    "business": "Hermes Business",
}
SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465
IMAP_HOST, IMAP_PORT = "imap.gmail.com", 993
TIMEOUT = 15
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,}$")


class GmailError(ValueError):
    """A user-facing, secret-free reason the credentials were not accepted."""


def _env_value(keys: tuple[str, ...]) -> str | None:
    """First non-empty value among ``keys``: the active profile's env files
    (shared secrets under its .env), then the process environment."""
    from api import profiles
    from api.shared_env import load_layered_env

    env = load_layered_env(Path(profiles.get_active_hermes_home()))
    for key in keys:
        if env.get(key):
            return env[key]
    for key in keys:
        if os.environ.get(key):
            return os.environ[key]
    return None


def normalise(address: str, app_password: str) -> tuple[str, str]:
    address = str(address or "").strip()
    password = re.sub(r"\s+", "", str(app_password or ""))
    if not _EMAIL.match(address):
        raise GmailError("Enter a valid Gmail address.")
    if not re.fullmatch(r"[A-Za-z0-9]{16}", password):
        raise GmailError("An app password is 16 letters (Google shows it in four groups of four).")
    return address, password


def verify_login(address: str, password: str) -> None:
    """Log in to Gmail SMTP and IMAP; raise :class:`GmailError` with a clear reason."""
    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=TIMEOUT, context=context) as smtp:
            smtp.login(address, password)
    except smtplib.SMTPAuthenticationError as error:
        raise GmailError("Gmail rejected this address and app password. Check both, and that 2-Step "
                         "Verification is on (app passwords need it).") from error
    except (OSError, smtplib.SMTPException, socket.timeout) as error:
        raise GmailError("Couldn't reach Gmail to send mail. Check the internet connection and try again.") from error
    try:
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=context, timeout=TIMEOUT)
    except (OSError, imaplib.IMAP4.error, socket.timeout) as error:
        raise GmailError("Sending works, but Gmail's inbox (IMAP) could not be reached.") from error
    try:
        imap.login(address, password)
    except imaplib.IMAP4.error as error:
        raise GmailError("Sending works, but reading replies failed. Turn IMAP on in Gmail → Settings → "
                         "Forwarding and POP/IMAP, then try again.") from error
    finally:
        try:
            imap.logout()
        except Exception:
            pass


# ---- reading the inbox through a flaky link ------------------------------------
# Gmail answers an IMAP check in about a second, but a single attempt can time
# out (a network blink, the machine waking from sleep). A check is retried once,
# and only a failure that lasts past a second scheduled check is reported, so a
# blink never shows as "Couldn't read the inbox".
RETRY_PAUSE = 3.0


def transient(error: BaseException) -> bool:
    """A network fault worth retrying, as opposed to a refused sign-in."""
    return isinstance(error, (OSError, imaplib.IMAP4.abort))


def with_retry(fetch: Callable, *args, sleep: Callable = None, **kwargs):
    """Run an IMAP read, once more after a short pause if the network failed."""
    import time

    try:
        return fetch(*args, **kwargs)
    except Exception as error:
        if not transient(error):
            raise
        (sleep or time.sleep)(RETRY_PAUSE)
        return fetch(*args, **kwargs)


def check_failed(state: dict, prefix: str, error: BaseException, now: int, *, report_after: int = 2) -> dict:
    """State updates after a failed inbox check: counted, and described only
    once it has failed ``report_after`` checks in a row (a refused sign-in is
    described at once)."""
    failures = int(state.get(f"{prefix}_failures") or 0) + 1
    since = int(state.get(f"{prefix}_failing_since") or now)
    if not transient(error):
        message = f"Gmail refused the sign-in ({type(error).__name__}). Reconnect Gmail in Settings."
    elif failures >= report_after:
        minutes = max(1, (now - since) // 60)
        message = f"Gmail hasn't answered for {minutes} min ({type(error).__name__}); still trying."
    else:
        message = ""
    return {f"{prefix}_failures": failures, f"{prefix}_failing_since": since, f"{prefix}_attempt": now,
            f"{prefix}_error": message}


def check_ok(prefix: str, now: int) -> dict:
    return {f"{prefix}_failures": 0, f"{prefix}_failing_since": None, f"{prefix}_attempt": now, f"{prefix}_error": ""}


def credentials() -> tuple[str | None, str | None]:
    """The connected sender address and app password (new keys, then legacy)."""
    return _env_value(ADDRESS_KEYS), _env_value(PASSWORD_KEYS)


def status() -> dict:
    address, password = credentials()
    from api.shared_env import shared_env_enabled

    return {"address": bool(address), "app_password": bool(password),
            "address_hint": _mask(address) if address else "",
            # Where a save lands: the shared file every profile reads, or this profile only.
            "scope": "shared" if shared_env_enabled() else "profile"}


def _mask(address: str) -> str:
    """``m***@gmail.com`` -- enough to recognise which account is connected."""
    local, _, domain = address.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def connect(address: str, app_password: str, *, verify: Callable[[str, str], None] = verify_login) -> dict:
    """Verify, then save both values. Nothing is written if verification fails."""
    from api import profiles
    from api.shared_env import write_env_values

    address, password = normalise(address, app_password)
    verify(address, password)
    # Save under the feature-neutral names and drop any legacy Job OS copies.
    write_env_values(profiles.get_active_hermes_home(), {
        ADDRESS_KEYS[0]: address, PASSWORD_KEYS[0]: password,
        **{key: None for key in (*ADDRESS_KEYS[1:], *PASSWORD_KEYS[1:])},
    })
    return status()


def disconnect() -> dict:
    from api import profiles
    from api.shared_env import write_env_values

    write_env_values(profiles.get_active_hermes_home(), {key: None for key in (*ADDRESS_KEYS, *PASSWORD_KEYS)})
    return status()


def sender_name(context: str) -> str:
    """The display name for a feature's email. Unknown features are refused
    rather than sent under a misleading name."""
    try:
        return SENDER_NAMES[context]
    except KeyError:
        raise ValueError(f"Unknown email sender context: {context!r}") from None


def _html_email(name: str, subject: str, body: str) -> str:
    """Render a conservative, client-safe companion for Hermes email.

    The plain-text part remains the canonical message for reply workflows and
    mail clients that do not render HTML.  This version deliberately uses
    table layout and inline styles because Gmail and Outlook discard modern
    layout rules unpredictably.
    """
    safe_subject = html.escape(str(subject or ""))
    safe_body = html.escape(str(body or "")).replace("\n", "<br>")
    return f"""<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{safe_subject}</title></head>
  <body style="margin:0;padding:0;background:#101412;color:#edf3ef;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#101412;padding:28px 12px;">
      <tr><td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:620px;background:#1a211d;border:1px solid #2c3530;border-radius:12px;overflow:hidden;">
          <tr><td style="padding:24px 28px 18px;border-bottom:1px solid #2c3530;">
            <p style="margin:0 0 6px;color:#78c7a3;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;">Hermes</p>
            <h1 style="margin:0;color:#edf3ef;font-size:20px;line-height:1.35;font-weight:650;">{safe_subject}</h1>
            <p style="margin:8px 0 0;color:#a9b4ad;font-size:13px;line-height:1.5;">{html.escape(name)}</p>
          </td></tr>
          <tr><td style="padding:24px 28px 28px;color:#edf3ef;font-size:15px;line-height:1.65;">{safe_body}</td></tr>
          <tr><td style="padding:16px 28px;border-top:1px solid #2c3530;color:#a9b4ad;font-size:12px;line-height:1.5;">Sent by Hermes. Keep this email for your records or reply where an action code is provided.</td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""


def send(context: str, to_address: str | None, subject: str, body: str, *,
         sender: Callable[[EmailMessage, str, str], None] | None = None) -> str:
    """Send ``body`` from the connected Gmail as ``"<feature name> <address>"``.

    ``to_address`` defaults to the connected account. Returns the recipient.
    """
    name = sender_name(context)
    address, password = credentials()
    if not address or not password:
        raise GmailError("Connect Gmail first.")
    recipient = str(to_address or "").strip() or address
    if not _EMAIL.match(recipient):
        raise GmailError("The recipient address is not valid.")
    message = EmailMessage()
    message["From"] = formataddr((name, address))
    message["To"] = recipient
    message["Subject"] = subject
    # Set by us rather than left to Gmail: mail without its own Date and
    # Message-ID scores as more likely-automated in spam filters.
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=address.rpartition("@")[2] or None)
    message.set_content(body)
    message.add_alternative(_html_email(name, subject, body), subtype="html")
    (sender or _smtp_send)(message, address, password)
    return recipient


def send_test(context: str, to_address: str | None = None, *,
              sender: Callable[[EmailMessage, str, str], None] | None = None) -> str:
    """A short test email from ``context``'s sender name."""
    name = sender_name(context)
    return send(context, to_address, f"{name}: test email",
                f"This is a test from {name}. Its notifications will arrive like this.", sender=sender)


def _smtp_send(message: EmailMessage, address: str, password: str) -> None:
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=TIMEOUT, context=ssl.create_default_context()) as smtp:
            smtp.login(address, password)
            smtp.send_message(message)
    except smtplib.SMTPAuthenticationError as error:
        raise GmailError("Gmail rejected the saved app password. Reconnect Gmail.") from error
    except (OSError, smtplib.SMTPException) as error:
        raise GmailError("Couldn't send the email. Try again in a moment.") from error
