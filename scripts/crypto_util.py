"""Symmetric encryption for the data files (AES-GCM, key from passphrase via PBKDF2).
The dashboard decrypts the same format in the browser with WebCrypto."""
import os, json, base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

ITERATIONS = 200_000

def _key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS)
    return kdf.derive(passphrase.encode("utf-8"))

def encrypt_json(obj, passphrase: str) -> str:
    salt, iv = os.urandom(16), os.urandom(12)
    ct = AESGCM(_key(passphrase, salt)).encrypt(iv, json.dumps(obj, ensure_ascii=False).encode("utf-8"), None)
    b64 = lambda b: base64.b64encode(b).decode()
    return json.dumps({"v": 1, "salt": b64(salt), "iv": b64(iv), "ct": b64(ct)})

def decrypt_json(blob: str, passphrase: str):
    d = json.loads(blob)
    b = lambda s: base64.b64decode(s)
    pt = AESGCM(_key(passphrase, b(d["salt"]))).decrypt(b(d["iv"]), b(d["ct"]), None)
    return json.loads(pt.decode("utf-8"))

def load(path, passphrase, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return decrypt_json(f.read(), passphrase)
    except Exception as e:
        print(f"warn: could not read {path}: {e}")
        return default

def save(path, passphrase, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(encrypt_json(obj, passphrase))
