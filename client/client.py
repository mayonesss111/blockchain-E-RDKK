# client.py --- Klien Kios untuk Pembuatan Kunci KDF & Penandatanganan Transaksi
import json
import sys
import time
import gc
import urllib.request
import urllib.error
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
        print("Penggunaan: python client.py [transaksi|mine|chain|resolve|kuota] [alamat_node] [argumen_lain...]")
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

        # Pembuatan Identitas Pengirim via KDF & ECC
        priv_k, pub_k = derive_ecc_keypair_from_pin(nik, pin)
        payload = f"{nik}:{jumlah}:{kios_id}:{timestamp}"
        
        sig = sign_data_ecc(priv_k, payload)
        pub_hex = get_public_key_hex(pub_k)

        print(f"\n[CP1] Identitas Petani Berhasil Dibuat via KDF (PBKDF2)")
        print(f"[CP1] Alamat Pengirim (Public Key): {pub_hex[:50]}...")
        print(f"[CP1] Private Key disimpan sementara di RAM (Ephemeral).")

        print(f"\n[CP2] Transaksi Dibuat: NIK {nik} menebus {jumlah} kg di {kios_id}")
        print(f"[CP2] Payload ditandatangani: {payload}")
        print(f"[CP2] Potongan Signature Petani: {sig[:60]}...")

        # Hapus kunci privat dari memori demi keamanan kios
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
            hasil = panggil(f"{alamat}/transactions/new", {"transaction": tx_obj})
            print(f"[CP3] Verifikasi Signature di Node: BERHASIL (Sah).")
            print(f"[CP4] Sukses! {hasil['pesan']}. Total di Mempool: {hasil['mempool_size']} transaksi.\n")
        except Exception as e:
            print(f"[CP3] Verifikasi Signature di Node: GAGAL / DITOLAK. Alasan: {e}\n")

    elif perintah == "mine":
        try:
            hasil = panggil(f"{alamat}/mine", {})
            print(f"Sukses! {hasil['pesan']} pada Blok #{hasil['block']['index']} (Validator: {hasil['block']['validator_id']})")
            print(f"Merkle Root : {hasil['block']['merkle_root']}")
            print(f"State Root  : {hasil['block']['state_root']}")
        except urllib.error.HTTPError as e:
            err_body = json.loads(e.read().decode("utf-8"))
            print(f"Gagal Menambang (HTTP {e.code}): {err_body.get('error', err_body)}")
        except Exception as e:
            print(f"Gagal Menambang Blok dari Mempool: {e}")

    elif perintah == "chain":
        try:
            from datetime import datetime
            hasil = panggil(f"{alamat}/chain")
            panjang = hasil['panjang']
            mempool_count = hasil.get('mempool_size', 0)

            print("\n" + "═" * 70)
            print(f" 📦 LEDGER BLOCKCHAIN E-RDKK | Total: {panjang} Blok | Mempool: {mempool_count} Tx")
            print("═" * 70)

            for b in hasil["chain"]:
                idx = b['index']
                val = b['validator_id']
                nonce = b['nonce']
                prev_hash = b['previous_hash'][:16] + "..." if b['previous_hash'] else "None"
                merkle = b['merkle_root'][:16] + "..."
                state_r = b['state_root'][:16] + "..."
                
                # Ubah format timestamp menjadi waktu yang mudah dibaca
                if b['timestamp'] == 0:
                    waktu_str = "Genesis (Awal Sistem)"
                else:
                    waktu_str = datetime.fromtimestamp(b['timestamp']).strftime('%Y-%m-%d %H:%M:%S')

                print(f"┌─ BLOK #{idx} " + "─" * (59 - len(str(idx))))
                print(f"│ Validator     : {val}")
                print(f"│ Waktu (WITA)  : {waktu_str}")
                print(f"│ Nonce (PoW)   : {nonce}")
                print(f"│ Previous Hash : {prev_hash}")
                print(f"│ Merkle Root   : {merkle}")
                print(f"│ State Root    : {state_r}")
                print(f"│ Data Transaksi:")

                txs = b['transactions_data']
                if idx == 0:
                    # Tampilan khusus untuk data alokasi kuota awal di Genesis Block
                    for nik, info in txs[0].items():
                        print(f"│   • [Alokasi Awal] NIK {nik} ({info['nama']}): {info['sisa_kuota_kg']} kg")
                else:
                    if not txs:
                        print("│   • (Tidak ada transaksi)")
                    for i, tx in enumerate(txs, 1):
                        print(f"│   {i}. NIK: {tx['nik_petani']} | Tebus: {tx['jumlah_kg']} kg | Kios: {tx['kios_id']}")
                
                print("└" + "─" * 68)
            print()
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