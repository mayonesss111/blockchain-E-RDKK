# client.py --- Klien Kios untuk Pembuatan Kunci KDF & Penandatanganan Transaksi
import json
import sys
import time
import gc
import urllib.request
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

def derive_ecc_keypair_from_pin(nik_petani: str, pin_petani: str):
    salt = f"eRDKK-SALT-{nik_petani}".encode('utf-8')
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    seed_bytes = kdf.derive(pin_petani.encode('utf-8'))
    order = 115792089210356248762697446949407573530086143415290314195533631308867097853951
    private_value = (int.from_bytes(seed_bytes, byteorder='big') % (order - 1)) + 1
    private_key = ec.derive_private_key(private_value, ec.SECP256R1())
    return private_key, private_key.public_key()

def get_public_key_hex(public_key):
    pub_bytes = public_key.public_bytes(
        encoding=Encoding.X962,
        format=PublicFormat.CompressedPoint
    )
    return pub_bytes.hex()

def sign_data_ecc(private_key, data_string: str):
    signature = private_key.sign(
        data_string.encode('utf-8'),
        ec.ECDSA(hashes.SHA256())
    )
    return signature.hex()

def panggil(url, data=None):
    if data is None:
        req = urllib.request.Request(url)
    else:
        req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read().decode("utf-8"))

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Penggunaan: python client.py [transaksi|chain|resolve|kuota] [alamat_node] [argumen_lain...]")
        sys.exit(1)

    perintah = sys.argv[1]
    alamat = sys.argv[2]
    if not alamat.startswith("http"):
        alamat = f"http://{alamat}"

    if perintah == "transaksi":
        if len(sys.argv) < 7:
            print("Format salah. Contoh: python client.py transaksi localhost:5001 7201001 123456 40 KIOS_PALU_01")
            sys.exit(1)
            
        nik = sys.argv[3]
        pin = sys.argv[4]
        jumlah = int(sys.argv[5])
        kios_id = sys.argv[6]
        timestamp = time.time()

        priv_k, pub_k = derive_ecc_keypair_from_pin(nik, pin)
        payload = f"{nik}:{jumlah}:{kios_id}:{timestamp}"
        
        sig = sign_data_ecc(priv_k, payload)
        pub_hex = get_public_key_hex(pub_k)

        del priv_k
        del pub_k
        gc.collect()
        print("[Kios Security] Private key berhasil dibersihkan dari RAM.")

        tx_obj = {
            "nik_petani": nik,
            "jumlah_kg": jumlah,
            "kios_id": kios_id,
            "timestamp": timestamp,
            "signature_petani": sig,
            "public_key_petani_hex": pub_hex
        }

        try:
            hasil = panggil(f"{alamat}/mine", {"transaction": tx_obj})
            print(f"Sukses! {hasil['pesan']} pada Blok #{hasil['block']['index']}")
        except Exception as e:
            print(f"Gagal Menambang/Mengesahkan Blok: {e}")

    elif perintah == "chain":
        try:
            hasil = panggil(f"{alamat}/chain")
            print(f"Panjang Rantai e-RDKK: {hasil['panjang']} Blok")
            for b in hasil["chain"]:
                print(f"  - Blok #{b['index']} | Validator: {b['validator_id']} | Transaksi: {b['transactions_data']}")
        except Exception as e:
            print(f"Gagal mengambil rantai: {e}")

    elif perintah == "resolve":
        try:
            hasil = panggil(f"{alamat}/resolve")
            print(f"Hasil Resolve -> Rantai diganti: {hasil.get('rantai_diganti', 'N/A')}, Panjang Rantai Sekarang: {hasil.get('panjang', 'N/A')} Blok")
        except Exception as e:
            print(f"Gagal melakukan resolve: {e}")

    elif perintah == "kuota":
        if len(sys.argv) < 4:
            print("Format salah. Contoh: python client.py kuota localhost:5001 7201001")
            sys.exit(1)
            
        nik = sys.argv[3]
        try:
            hasil = panggil(f"{alamat}/cek_kuota/{nik}")
            print(f"=== INFORMASI KUOTA E-RDKK ===")
            print(f"NIK Petani     : {hasil['nik_petani']}")
            print(f"Sisa Kuota     : {hasil['sisa_kuota_kg']} Kg")
        except Exception as e:
            print(f"Gagal mengecek kuota: {e}")