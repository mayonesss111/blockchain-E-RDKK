# crypto_utils.py
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

def get_public_key_from_hex(pub_hex: str):
    return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes.fromhex(pub_hex))

def get_public_key_hex(public_key):
    pub_bytes = public_key.public_bytes(
        encoding=Encoding.X962,
        format=PublicFormat.CompressedPoint
    )
    return pub_bytes.hex()

def verify_signature_ecc(public_key, data_string: str, signature_hex: str) -> bool:
    try:
        signature = bytes.fromhex(signature_hex)
        public_key.verify(
            signature,
            data_string.encode('utf-8'),
            ec.ECDSA(hashes.SHA256())
        )
        return True
    except Exception:
        return False