"""BcryptPasswordHasher — password hashing for accounts (PRD §9.4).

Wraps the ``bcrypt`` library directly (no passlib) to avoid version
incompatibilities. bcrypt has a 72-byte input limit; we pre-hash with
SHA-256 so long passwords are still fully mixed in.
"""

from __future__ import annotations

import base64
import hashlib

import bcrypt


def _prepare(password: str) -> bytes:
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


class BcryptPasswordHasher:
    def hash(self, password: str) -> str:
        return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("utf-8")

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            return bcrypt.checkpw(_prepare(password), password_hash.encode("utf-8"))
        except ValueError:
            return False
