r"""Encrypt / decrypt backup archives (public-key, so the laptop can't read its own backups).

Scheme (hybrid): a fresh random AES-256-GCM key per file encrypts the archive;
that key is wrapped with an RSA-4096 PUBLIC key (OAEP-SHA256). The machine that
makes backups only has the public key — it can create backups but not read them.
The PRIVATE key is needed only to restore and must live OFF the machine
(password manager + a second offline copy). Lose it = every backup is unreadable.

File format (.enc):  MAGIC | u16 wrapped-key length | wrapped key | 12-byte nonce |
                     AES-GCM ciphertext+tag   (MAGIC is authenticated as AAD)

CLI:
    python scripts/backup_crypto.py generate <public_out.pem> <private_out.pem>
    python scripts/backup_crypto.py encrypt  <file> <public.pem>        # -> <file>.enc, deletes <file>
    python scripts/backup_crypto.py decrypt  <file.enc> <private.pem> <out>
"""
import os
import struct
import sys
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"DPBACKUP1\n"
_OAEP = padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                     algorithm=hashes.SHA256(), label=None)


def generate_keypair(public_out, private_out):
    """Write a new RSA-4096 keypair. The private key file is created owner-only
    where the OS supports it; move it off this machine right away."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    Path(public_out).write_bytes(key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    private_pem = key.private_bytes(serialization.Encoding.PEM,
                                    serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption())
    fd = os.open(private_out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)   # never overwrite
    with os.fdopen(fd, "wb") as fh:
        fh.write(private_pem)


def encrypt_bytes(data, public_key_pem):
    public_key = serialization.load_pem_public_key(public_key_pem)
    data_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    wrapped = public_key.encrypt(data_key, _OAEP)
    return MAGIC + struct.pack(">H", len(wrapped)) + wrapped + nonce + \
        AESGCM(data_key).encrypt(nonce, data, MAGIC)


def decrypt_bytes(blob, private_key_pem, passphrase=None):
    if not blob.startswith(MAGIC):
        raise ValueError("not a MyDentalPortal encrypted backup")
    offset = len(MAGIC)
    (wrapped_len,) = struct.unpack(">H", blob[offset:offset + 2])
    offset += 2
    wrapped = blob[offset:offset + wrapped_len]
    offset += wrapped_len
    nonce = blob[offset:offset + 12]
    private_key = serialization.load_pem_private_key(private_key_pem, password=passphrase)
    data_key = private_key.decrypt(wrapped, _OAEP)
    return AESGCM(data_key).decrypt(nonce, blob[offset + 12:], MAGIC)   # raises if tampered


def encrypt_file(path, public_key_path):
    """Encrypt `path` to `path.enc`, then delete the plaintext. Returns the .enc path."""
    src = Path(path)
    dst = src.with_name(src.name + ".enc")
    dst.write_bytes(encrypt_bytes(src.read_bytes(), Path(public_key_path).read_bytes()))
    src.unlink()
    return dst


def decrypt_file(path, private_key_path, out_path, passphrase=None):
    Path(out_path).write_bytes(
        decrypt_bytes(Path(path).read_bytes(), Path(private_key_path).read_bytes(), passphrase))
    return Path(out_path)


def main(argv):
    cmd, *args = argv or [""]
    if cmd == "generate" and len(args) == 2:
        generate_keypair(*args)
        print(f"Public key  -> {args[0]}  (stays on this machine; used to encrypt)")
        print(f"PRIVATE key -> {args[1]}  MOVE IT OFF THIS MACHINE NOW (password manager + an")
        print("               offline copy), then delete it here. Lose it = backups unreadable.")
        return 0
    if cmd == "encrypt" and len(args) == 2:
        print(encrypt_file(*args))
        return 0
    if cmd == "decrypt" and len(args) == 3:
        print(decrypt_file(*args))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
