"""Verschlüsselt das fertige Video mit einem Passwort, damit es öffentlich liegen kann.

    VIDEO_PASSWORT=… python3 video/encrypt.py video/antibiotika_video.mp4

Schreibt video/antibiotika_video.enc (12 Byte IV + AES-256-GCM-Chiffrat) und
video/zugang.js (Salt, Iterationen und ein kleiner Prüfwert, mit dem die Seite
ein falsches Passwort erkennt, bevor sie 34 MB lädt). Das Passwort selbst steht
nirgends im Repo; index.html leitet den Schlüssel im Browser genauso ab.
"""
import base64
import getpass
import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

HERE = Path(__file__).resolve().parent
ITERATIONS = 600_000
CHECK = b"Antibiotika"

b64 = lambda b: base64.b64encode(b).decode()


def main(src):
    password = os.environ.get("VIDEO_PASSWORT") or getpass.getpass("Passwort: ")
    salt = os.urandom(16)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS).derive(password.encode())
    aes = AESGCM(key)
    iv = os.urandom(12)
    (HERE / "antibiotika_video.enc").write_bytes(iv + aes.encrypt(iv, Path(src).read_bytes(), None))
    civ = os.urandom(12)
    zugang = {"salt": b64(salt), "iterations": ITERATIONS, "checkIv": b64(civ), "check": b64(aes.encrypt(civ, CHECK, None))}
    (HERE / "zugang.js").write_text("// Erzeugt von encrypt.py – enthält nicht das Passwort.\nwindow.ZUGANG = "
                                    + json.dumps(zugang) + ";\n", encoding="utf-8")
    print("verschlüsselt:", HERE / "antibiotika_video.enc")


if __name__ == "__main__":
    main(sys.argv[1])
