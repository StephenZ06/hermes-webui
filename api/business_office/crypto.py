"""Encryption at rest for provider tokens and app secrets.

AES-256-GCM with the owning record as associated data, so a ciphertext copied
onto another business or provider fails to decrypt instead of quietly granting
that business the account.

The key comes from ``HERMES_BUSINESS_OFFICE_KEY`` (urlsafe base64 of 32 bytes)
or, without it, from a 0600 file next to the state. The file protects against
a copied database, not against something that can already read the whole state
directory; :func:`key_source` lets the UI say which one is in use.
"""

from __future__ import annotations

import base64
import binascii
import os
import secrets
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_ENV = "HERMES_BUSINESS_OFFICE_KEY"
KEY_FILE = "business_office.key"
_VERSION = "v1"


class SecretError(RuntimeError):
    """A stored secret cannot be read; callers treat the connection as unauthorized."""


def _state_dir() -> Path:
    from api import config

    return Path(config.STATE_DIR)


def key_source() -> str:
    return "env" if os.environ.get(KEY_ENV) else "file"


def _key_from_env(raw: str) -> bytes:
    try:
        key = base64.urlsafe_b64decode(raw.encode("ascii"))
    except (ValueError, binascii.Error) as error:
        raise SecretError(f"{KEY_ENV} is not valid base64") from error
    if len(key) != 32:
        raise SecretError(f"{KEY_ENV} must decode to 32 bytes")
    return key


def _key_from_file() -> bytes:
    path = _state_dir() / KEY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        key = path.read_bytes()
        if len(key) != 32:
            raise SecretError("The Business Office key file is damaged") from None
        return key
    key = secrets.token_bytes(32)
    with os.fdopen(fd, "wb") as handle:
        handle.write(key)
    return key


def _key() -> bytes:
    raw = os.environ.get(KEY_ENV)
    return _key_from_env(raw) if raw else _key_from_file()


def encrypt(plain: str, *, context: str) -> str:
    nonce = secrets.token_bytes(12)
    sealed = AESGCM(_key()).encrypt(nonce, plain.encode("utf-8"), context.encode("utf-8"))
    return f"{_VERSION}:" + base64.urlsafe_b64encode(nonce + sealed).decode("ascii")


def decrypt(token: str, *, context: str) -> str:
    version, _, body = str(token or "").partition(":")
    if version != _VERSION or not body:
        raise SecretError("Unknown secret format")
    try:
        raw = base64.urlsafe_b64decode(body.encode("ascii"))
        plain = AESGCM(_key()).decrypt(raw[:12], raw[12:], context.encode("utf-8"))
    except (ValueError, binascii.Error, InvalidTag) as error:
        raise SecretError("A stored secret could not be decrypted") from error
    return plain.decode("utf-8")
