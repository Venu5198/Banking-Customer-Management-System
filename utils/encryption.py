"""
Encryption utilities for sensitive fields.
- National ID / Passport: Fernet symmetric encryption (reversible for authorized users)
- Hash: SHA-256 for duplicate detection without decryption
NEVER store plaintext national IDs. NEVER log decrypted values.
"""

import os
import hashlib
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()


def _get_fernet() -> Fernet:
    """Load Fernet cipher from environment. Fails loudly if key is missing."""
    key = os.getenv("FERNET_KEY")
    if not key:
        raise RuntimeError(
            "FERNET_KEY not set in environment. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode())


def encrypt_national_id(national_id: str) -> str:
    """Encrypt national ID for storage. Returns base64 ciphertext string."""
    f = _get_fernet()
    return f.encrypt(national_id.encode()).decode()


def decrypt_national_id(encrypted: str) -> str:
    """Decrypt national ID. Only call for authorized viewing (Manager/Admin)."""
    f = _get_fernet()
    return f.decrypt(encrypted.encode()).decode()


def hash_national_id(national_id: str) -> str:
    """
    One-way SHA-256 hash of national ID for duplicate detection.
    Salted with a constant app prefix to prevent rainbow table attacks.
    """
    salt = os.getenv("SECRET_KEY", "default-salt")
    return hashlib.sha256(f"{salt}:{national_id}".encode()).hexdigest()
