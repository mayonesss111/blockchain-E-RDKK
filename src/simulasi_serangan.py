import sys
import json
import time
import urllib.request
import urllib.error
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

def derive_ecc_keypair_from_pin(nik_petani: str, pin_petani: str):
    salt = f"eRDKK-SALT-{nik_petani}".encode('utf-8')
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
    seed_bytes = kdf.derive(pin_petani.encode('utf-8'))
    order = 115792089210356248762697446949407573530086143415290314195533631308867097853951
    private_value = (int.from_bytes(seed_bytes, byteorder='big') % (order - 1)) + 1
    private_key = ec.derive_private_key(private_value, ec.SECP256R1())
    return private_key, private_key.public_key()

def get_public_key_hex(public_key):
    return public_key.public_bytes(encoding=Encoding.X962, format=PublicFormat.CompressedPoint).hex()

def sign_data_ecc(private_key, data_string: str):
    return private_key.sign(data_string.encode('utf-8'), ec.ECDSA(hashes.SHA256())).hex()

def kirim_post(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))
    except Exception as e:
        return 0, {"error": str(e)}

def buat_paket_tx(nik, pin, jumlah, kios_id, ts=None):
    if ts is None:
        ts = time.time()
    priv_k, pub_k = derive_ecc_keypair_from_pin(nik, pin)
    payload = f"{nik}:{jumlah}:{kios_id}:{ts}"
    sig = sign_data_ecc(priv_k, payload)
    pub_hex = get_public_key_hex(pub_k)
    return {
        "transaction": {
            "nik_petani": nik,
            "jumlah_kg": jumlah,
            "kios_id": kios_id,
            "timestamp": ts,
            "signature_petani": sig,
            "public_key_petani_hex": pub_hex
        }
    }

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Penggunaan: python3 simulasi_serangan.py [IP_NODE_1:PORT] [IP_NODE_2:PORT]")
        print("Contoh    : python3 simulasi_serangan.py 192.168.1.7:8000 192.168.1.8:8000")
        sys.exit(1)

    NODE_1 = sys.argv[1]  # VAL_KEMENTAN
    NODE_2 = sys.argv[2]  # VAL_PT_PUPUK

    print("=================================================================")
    print("   SIMULASI OTOMATIS SERANGAN & VALIDASI SMART CONTRACT E-RDKK   ")
    print("=================================================================\n")

    # --------------------------------------------------------------------------
    # SERANGAN 1: MANIPULASI DATA TRANSAKSI (TAMPERING / SIGNATURE PALSU)
    # --------------------------------------------------------------------------
    print("[TEST 1] Serangan Manipulasi Nominal Transaksi (Ubah 20 kg -> 50 kg setelah TTD)...")
    tx_tamper = buat_paket_tx("7201001", "123456", 20, "KIOS_PALU_01")
    tx_tamper["transaction"]["jumlah_kg"] = 50  # Hacker mengubah jumlah tanpa tanda tangan ulang
    status, res = kirim_post(f"http://{NODE_1}/transactions/new", tx_tamper)
    print(f"   -> Hasil (Harus HTTP 400): HTTP {status} | Pesan: {res.get('error')}\n")
    time.sleep(1)

    # --------------------------------------------------------------------------
    # SERANGAN 2: PELANGGARAN SMART CONTRACT (MELEBIHI BATAS 50 KG)
    # --------------------------------------------------------------------------
    print("[TEST 2] Pelanggaran Smart Contract: Tebus 75 kg (Batas maksimal 50 kg)...")
    tx_over = buat_paket_tx("7201001", "123456", 75, "KIOS_PALU_01")
    status, res = kirim_post(f"http://{NODE_1}/transactions/new", tx_over)
    print(f"   -> Hasil (Harus HTTP 400): HTTP {status} | Pesan: {res.get('error')}\n")
    time.sleep(1)

    # --------------------------------------------------------------------------
    # SERANGAN 3: PELANGGARAN SMART CONTRACT (ZONASI WILAYAH KIOS)
    # --------------------------------------------------------------------------
    print("[TEST 3] Pelanggaran Smart Contract: Petani Palu (7201) menebus di Donggala...")
    tx_zonasi = buat_paket_tx("7201001", "123456", 20, "KIOS_DONGGALA_01")
    status, res = kirim_post(f"http://{NODE_1}/transactions/new", tx_zonasi)
    print(f"   -> Hasil (Harus HTTP 400): HTTP {status} | Pesan: {res.get('error')}\n")
    time.sleep(1)

    # --------------------------------------------------------------------------
    # TRANSAKSI SAH + SERANGAN 4: COOLDOWN & REPLAY ATTACK
    # --------------------------------------------------------------------------
    print("[TEST 4] Mengirim Transaksi SAH (30 kg) lalu mencoba Cooldown & Replay Attack...")
    tx_sah = buat_paket_tx("7201001", "123456", 30, "KIOS_PALU_01")
    status_sah, res_sah = kirim_post(f"http://{NODE_1}/transactions/new", tx_sah)
    print(f"   -> Transaksi Sah (Harus HTTP 201): HTTP {status_sah} | Pesan: {res_sah.get('pesan')}")
    time.sleep(1)

    # Uji Cooldown (Langsung kirim transaksi baru < 30 detik)
    tx_cepat = buat_paket_tx("7201001", "123456", 10, "KIOS_PALU_01")
    status_cd, res_cd = kirim_post(f"http://{NODE_1}/transactions/new", tx_cepat)
    print(f"   -> Uji Cooldown (Harus HTTP 400) : HTTP {status_cd} | Pesan: {res_cd.get('error')}\n")
    time.sleep(1)

    # --------------------------------------------------------------------------
    # TEST 5: CHECKPOINT 10 (BROADCAST BLOK VALID LINTAS MESIN)
    # --------------------------------------------------------------------------
    print("[TEST 5 - CP10] Mining Blok #1 di Node 2 (VAL_PT_PUPUK) & Broadcast ke Node 1...")
    status_mine, res_mine = kirim_post(f"http://{NODE_2}/mine", {})
    print(f"   -> Hasil Mining (Harus HTTP 201): HTTP {status_mine} | Pesan: {res_mine.get('pesan', res_mine.get('error'))}\n")
    time.sleep(2)

    # --------------------------------------------------------------------------
    # SERANGAN 6: REPLAY ATTACK SETELAH BLOK DITAMBANG
    # --------------------------------------------------------------------------
    print("[TEST 6] Serangan Replay Attack (Mengirim ulang paket transaksi sah yang sudah masuk blok)...")
    status_rep, res_rep = kirim_post(f"http://{NODE_1}/transactions/new", tx_sah)
    print(f"   -> Hasil Replay (Harus HTTP 400): HTTP {status_rep} | Pesan: {res_rep.get('error')}\n")
    time.sleep(1)

    # --------------------------------------------------------------------------
    # SERANGAN 7: CHECKPOINT 11 (PENOLAKAN BLOK PALSU LINTAS MESIN)
    # --------------------------------------------------------------------------
    print("[TEST 7 - CP11] Menembakkan Blok Palsu (Manipulasi State & Signature) ke Node 2...")
    blok_palsu = {
        "index": 2,
        "timestamp": time.time(),
        "transactions_data": [{"nik_petani": "7201001", "jumlah_kg": 99999}],
        "merkle_root": "f" * 64,
        "validator_id": "VAL_DINAS_PERTANIAN",
        "previous_hash": "hash_palsu_tidak_valid",
        "nonce": 0,
        "state_root": "f" * 64,
        "signature_validator": "00" * 64
    }
    status_fake, res_fake = kirim_post(f"http://{NODE_2}/block", blok_palsu)
    print(f"   -> Hasil Blok Palsu (Harus HTTP 409): HTTP {status_fake} | Pesan: {res_fake.get('pesan')}\n")

    print("=================================================================")
    print("   SELURUH RANGKAIAN PENGUJIAN KEAMANAN & LINTAS MESIN SELESAI    ")
    print("=================================================================")
