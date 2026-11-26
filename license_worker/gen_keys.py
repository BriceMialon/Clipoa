"""Génère la paire Ed25519 du serveur de licence.
Clé privée -> secret LICENSE_SIGNING_KEY du Worker. Clé publique -> DEFAULT_PUBKEY_HEX de core/license.py.
Usage : python3 gen_keys.py   (nécessite le paquet cryptography)"""
import base64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization as s

k = Ed25519PrivateKey.generate()
priv = k.private_bytes(s.Encoding.DER, s.PrivateFormat.PKCS8, s.NoEncryption())
pub = k.public_key().public_bytes(s.Encoding.Raw, s.PublicFormat.Raw)
print("LICENSE_SIGNING_KEY (secret, ne jamais commiter) :\n" + base64.b64encode(priv).decode())
print("\nDEFAULT_PUBKEY_HEX (core/license.py) :\n" + pub.hex())
