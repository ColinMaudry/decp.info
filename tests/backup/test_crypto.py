import pytest
from cryptography.fernet import Fernet

from src.backup.crypto import decrypt, encrypt


def test_roundtrip():
    key = Fernet.generate_key().decode()
    data = b"contenu de la base sqlite"
    assert decrypt(encrypt(data, key), key) == data


def test_wrong_key_fails():
    data = b"secret"
    token = encrypt(data, Fernet.generate_key().decode())
    with pytest.raises(Exception):
        decrypt(token, Fernet.generate_key().decode())
