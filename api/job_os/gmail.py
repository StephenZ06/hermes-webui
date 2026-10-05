"""Gmail credentials for Job OS notifications.

The address and app password are verified with a real login (SMTP for
sending, IMAP for reading replies) *before* they are saved, then written with
:func:`api.shared_env.write_env_values` -- to the shared secrets file every
profile reads, when that layer is enabled. The password is never returned to
the browser or logged; status is reported as booleans.
"""

from __future__ import annotations

import imaplib
import re
import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from typing import Callable

from api.job_os.env import profile_env_value

ADDRESS_KEY = "JOB_OS_GMAIL_ADDRESS"
PASSWORD_KEY = "JOB_OS_GMAIL_APP_PASSWORD"
SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465
IMAP_HOST, IMAP_PORT = "imap.gmail.com", 993
TIMEOUT = 15
SENDER_NAME = "Hermes Jobs"
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,}$")


class GmailError(ValueError):
    """A user-facing, secret-free reason the credentials were not accepted."""


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


def status() -> dict:
    address, _ = profile_env_value(ADDRESS_KEY)
    password, _ = profile_env_value(PASSWORD_KEY)
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
    write_env_values(profiles.get_active_hermes_home(), {ADDRESS_KEY: address, PASSWORD_KEY: password})
    return status()


def disconnect() -> dict:
    from api import profiles
    from api.shared_env import write_env_values

    write_env_values(profiles.get_active_hermes_home(), {ADDRESS_KEY: None, PASSWORD_KEY: None})
    return status()


def send_test(to_address: str | None = None, *, sender: Callable[[EmailMessage, str, str], None] | None = None) -> str:
    """Send a short test email (to ``to_address`` or the connected account)."""
    address, _ = profile_env_value(ADDRESS_KEY)
    password, _ = profile_env_value(PASSWORD_KEY)
    if not address or not password:
        raise GmailError("Connect Gmail first.")
    recipient = str(to_address or "").strip() or address
    if not _EMAIL.match(recipient):
        raise GmailError("The 'Send to' address is not valid.")
    message = EmailMessage()
    message["From"] = formataddr((SENDER_NAME, address))
    message["To"] = recipient
    message["Subject"] = "Hermes Jobs: test notification"
    message.set_content("This is a test from Hermes Jobs. New job matches and digests will arrive like this.")
    (sender or _smtp_send)(message, address, password)
    return recipient


def _smtp_send(message: EmailMessage, address: str, password: str) -> None:
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=TIMEOUT, context=ssl.create_default_context()) as smtp:
            smtp.login(address, password)
            smtp.send_message(message)
    except smtplib.SMTPAuthenticationError as error:
        raise GmailError("Gmail rejected the saved app password. Reconnect Gmail.") from error
    except (OSError, smtplib.SMTPException) as error:
        raise GmailError("Couldn't send the test email. Try again in a moment.") from error
