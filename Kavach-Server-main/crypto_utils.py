import os
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305


def load_aes_key():
    with open("keys/aes.key", "rb") as f:
        return f.read()

def aes_encrypt_text(plaintext: str) -> bytes:
    key = load_aes_key()
    iv = os.urandom(16)  # AES block size = 16 bytes

    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(plaintext.encode()) + padder.finalize()

    cipher = Cipher(
        algorithms.AES(key),
        modes.CBC(iv),
        backend=default_backend()
    )

    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()

    return iv + ciphertext

def aes_decrypt_text(encrypted_data: bytes) -> str:
    key = load_aes_key()
    iv = encrypted_data[:16]
    ciphertext = encrypted_data[16:]

    cipher = Cipher(
        algorithms.AES(key),
        modes.CBC(iv),
        backend=default_backend()
    )

    decryptor = cipher.decryptor()
    padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    unpadder = padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()

    return plaintext.decode()

def load_chacha_key():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    key_path = os.path.join(base_dir, "keys", "chacha.key")
    with open(key_path, "rb") as f:
        return f.read()

def chacha_encrypt_text(plaintext: str) -> bytes:
    key = load_chacha_key()
    chacha = ChaCha20Poly1305(key)

    nonce = os.urandom(12)  # REQUIRED size
    ciphertext = chacha.encrypt(nonce, plaintext.encode(), None)

    return nonce + ciphertext

def chacha_decrypt_text(encrypted_data: bytes) -> str:
    key = load_chacha_key()
    chacha = ChaCha20Poly1305(key)

    nonce = encrypted_data[:12]
    ciphertext = encrypted_data[12:]

    plaintext = chacha.decrypt(nonce, ciphertext, None)
    return plaintext.decode()



if __name__ == "__main__":
    msg = "SOS ALERT: GPS LOCATION"
    enc = aes_encrypt_text(msg)
    dec = aes_decrypt_text(enc)

    print("Original:", msg)
    print("Encrypted:", enc)
    print("Decrypted:", dec)

if __name__ == "__main__":
    msg = "HELLO SERVER, THIS IS ENCRYPTED"
    enc = chacha_encrypt_text(msg)
    dec = chacha_decrypt_text(enc)

    print("Original:", msg)
    print("Encrypted", enc)
    print("Decrypted:", dec)
