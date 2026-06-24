from cryptography.fernet import Fernet


def encrypt(data: bytes, key: str) -> bytes:
    return Fernet(key.encode()).encrypt(data)


def decrypt(token: bytes, key: str) -> bytes:
    return Fernet(key.encode()).decrypt(token)
