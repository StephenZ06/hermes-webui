"""Job OS's view of the Hermes-wide Gmail sender (api/mailer.py).

Jobs email goes out as "Hermes Jobs"; connecting, status and the test email
are the shared mailer's, scoped to the ``jobs`` sender name.
"""

from __future__ import annotations

from typing import Callable

from api import mailer
from api.mailer import GmailError, connect, disconnect, normalise, status  # noqa: F401 - re-exported

ADDRESS_KEY = mailer.ADDRESS_KEYS[0]
PASSWORD_KEY = mailer.PASSWORD_KEYS[0]
CONTEXT = "jobs"


def verify_login(address: str, password: str) -> None:
    mailer.verify_login(address, password)


def send_test(to_address: str | None = None, *, context: str = CONTEXT, sender: Callable | None = None) -> str:
    return mailer.send_test(context, to_address, sender=sender)
