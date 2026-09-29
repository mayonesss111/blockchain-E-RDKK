# node.py --- Node Validator e-RDKK dengan PoA Round-Robin, Multi-Node Broadcast & Resolve
import hashlib
import json
import sys
import time
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

PORT = 0
PEERS = []
CHAIN = []

VALIDATORS_ORDER = ["VAL_KEMENTAN", "VAL_PT_PUPUK", "VAL_DINAS_PERTANIAN"]
VALIDATOR_PUB_KEYS_HEX = {}
VALIDATOR_PRIV_KEYS = {}

# Konstanta Order Kurva SECP256R1 yang valid
SECP256R1_ORDER = 115792089210356248762697446949407573530086143415290314195533631308867097853951

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

class Block:
    def __init__(self, index, transactions_data, validator_id, previous_hash=None, nonce=0):
        self.index = index
        self.timestamp = time.time()
        self.transactions_data = transactions_data
        self.validator_id = validator_id
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.signature_validator = None

    def get_block_header(self):
        return json.dumps({
            'index': self.index,
            'timestamp': self.timestamp,
            'transactions_data': self.transactions_data,
            'validator_id': self.validator_id,
            'previous_hash': self.previous_hash,
            'nonce': self.nonce
        }, sort_keys=True)

    def compute_hash(self):
        payload = self.get_block_header().encode('utf-8')
        return hashlib.sha256(payload).hexdigest()

    def to_dict(self):
        return {
            'index': self.index,
            'timestamp': self.timestamp,
            'transactions_data': self.transactions_data,
            'validator_id': self.validator_id,
            'previous_hash': self.previous_hash,
            'nonce': self.nonce,
            'signature_validator': self.signature_validator
        }

def genesis_block():
    db_kuota_pemerintah = {
        "7201001": {"nama": "Pak Farmer A", "sisa_kuota_kg": 100},
        "7201002": {"nama": "Pak Farmer B", "sisa_kuota_kg": 100}
    }
    b = Block(0, [db_kuota_pemerintah], "VAL_KEMENTAN", previous_hash="0"*64, nonce=0)
    sig = VALIDATOR_PRIV_KEYS["VAL_KEMENTAN"].sign(b.compute_hash().encode('utf-8'), ec.ECDSA(hashes.SHA256()))
    b.signature_validator = sig.hex()
    return b

def get_scheduled_validator(block_index: int) -> str:
    return VALIDATORS_ORDER[block_index % len(VALIDATORS_ORDER)]

def is_chain_valid(chain):
    for i in range(1, len(chain)):
        curr = chain[i]
        prev = chain[i - 1]
        
        b_obj = Block(curr['index'], curr['transactions_data'], curr['validator_id'], curr['previous_hash'], curr['nonce'])
        b_obj.timestamp = curr['timestamp']
        
        prev_block_obj = Block(prev['index'], prev['transactions_data'], prev['validator_id'], prev['previous_hash'], prev['nonce'])
        prev_block_obj.timestamp = prev['timestamp']
        prev_hash_computed = prev_block_obj.compute_hash()
        
        if curr['previous_hash'] != prev_hash_computed:
            return False
        
        if curr['validator_id'] != get_scheduled_validator(curr['index']):
            return False
            
        val_pub_hex = VALIDATOR_PUB_KEYS_HEX.get(curr['validator_id'])
        if not val_pub_hex:
            return False
            
        val_pub_key = get_public_key_from_hex(val_pub_hex)
        sig_val = bytes.fromhex(curr['signature_validator'])
        try:
            val_pub_key.verify(sig_val, b_obj.compute_hash().encode('utf-8'), ec.ECDSA(hashes.SHA256()))
        except Exception:
            return False
    return True

def broadcast_block(block_dict):
    for peer in PEERS:
        try:
            data = json.dumps(block_dict).encode("utf-8")
            req = urllib.request.Request(f"http://{peer}/block", data=data, headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=3)
            print(f"[{PORT}] Berhasil broadcast blok ke peer: {peer}")
        except Exception as e:
            print(f"[{PORT}] Gagal broadcast ke peer {peer}: {e}")

def resolve_conflicts():
    terpanjang = CHAIN
    berubah = False
    for peer in PEERS:
        try:
            req = urllib.request.Request(f"http://{peer}/chain")
            with urllib.request.urlopen(req, timeout=3) as res:
                kandidat = json.loads(res.read().decode("utf-8"))["chain"]
                if len(kandidat) > len(terpanjang) and is_chain_valid(kandidat):
                    terpanjang = kandidat
                    berubah = True
        except Exception:
            pass
    if berubah:
        CHAIN[:] = terpanjang
        return True
    return False

def get_sisa_kuota_petani(nik_petani: str) -> int:
    """
    Menghitung sisa kuota petani dengan menelusuri seluruh rantai (chain)
    dari Genesis Block hingga blok terakhir.
    """
    genesis_tx = CHAIN[0]['transactions_data'][0]
    if nik_petani in genesis_tx:
        kuota_awal = genesis_tx[nik_petani]['sisa_kuota_kg']
    else:
        return -1 # Petani tidak terdaftar

    total_diambil = 0
    for i in range(1, len(CHAIN)):
        block = CHAIN[i]
        for tx in block['transactions_data']:
            if tx.get('nik_petani') == nik_petani:
                total_diambil += tx.get('jumlah_kg', 0)
                
    return kuota_awal - total_diambil

class NodeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _balas(self, kode, isi):
        badan = json.dumps(isi, indent=2).encode("utf-8")
        self.send_response(kode)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(badan)))
        self.end_headers()
        self.wfile.write(badan)

    def do_GET(self):
        if self.path == "/chain":
            self._balas(200, {"panjang": len(CHAIN), "chain": CHAIN})
        elif self.path == "/resolve":
            status_ubah = resolve_conflicts()
            self._balas(200, {"rantai_diganti": status_ubah, "panjang": len(CHAIN)})
        elif self.path.startswith("/cek_kuota/"):
            nik = self.path.split("/")[-1]
            sisa = get_sisa_kuota_petani(nik)
            if sisa == -1:
                self._balas(404, {"error": "NIK Petani tidak ditemukan dalam alokasi subsidi."})
            else:
                self._balas(200, {"nik_petani": nik, "sisa_kuota_kg": sisa})
        else:
            self._balas(404, {"error": "Endpoint tidak dikenal"})

    def do_POST(self):
        panjang = int(self.headers.get("Content-Length", 0))
        isi = json.loads(self.rfile.read(panjang) or b"{}")

        if self.path == "/mine":
            induk = CHAIN[-1]
            next_index = induk["index"] + 1
            expected_val = get_scheduled_validator(next_index)
            
            if expected_val not in VALIDATOR_PRIV_KEYS:
                self._balas(403, {"error": f"Node ini bukan giliran validator {expected_val}!"})
                return

            tx_data = isi.get("transaction", {})
            nik = tx_data['nik_petani']
            jumlah_diminta = tx_data['jumlah_kg']
            
            # Validasi ketersediaan sisa kuota sebelum memproses transaksi
            sisa_kuota_sekarang = get_sisa_kuota_petani(nik)
            if sisa_kuota_sekarang == -1:
                self._balas(400, {"error": "NIK Petani tidak terdaftar di sistem kuota subsidi!"})
                return
            if jumlah_diminta > sisa_kuota_sekarang:
                self._balas(400, {"error": f"Transaksi ditolak! Kuota tidak cukup. Sisa kuota: {sisa_kuota_sekarang} kg"})
                return

            payload_str = f"{nik}:{jumlah_diminta}:{tx_data['kios_id']}:{tx_data['timestamp']}"
            
            try:
                farmer_pub_key = get_public_key_from_hex(tx_data['public_key_petani_hex'])
                if not verify_signature_ecc(farmer_pub_key, payload_str, tx_data['signature_petani']):
                    self._balas(400, {"error": "Tanda tangan digital petani tidak sah!"})
                    return
            except Exception as e:
                self._balas(400, {"error": f"Internal error: {str(e)}"})
                return

            prev_block_obj = Block(induk['index'], induk['transactions_data'], induk['validator_id'], induk['previous_hash'], induk['nonce'])
            prev_block_obj.timestamp = induk['timestamp']
            prev_hash = prev_block_obj.compute_hash()

            block = Block(
                index=next_index,
                transactions_data=[tx_data],
                validator_id=expected_val,
                previous_hash=prev_hash,
                nonce=next_index
            )
            
            sig_val = VALIDATOR_PRIV_KEYS[expected_val].sign(block.compute_hash().encode('utf-8'), ec.ECDSA(hashes.SHA256()))
            block.signature_validator = sig_val.hex()
            
            block_dict = block.to_dict()
            CHAIN.append(block_dict)
            print(f"[{PORT}] Blok #{next_index} berhasil ditambang oleh Validator: {expected_val}")
            
            broadcast_block(block_dict)
            self._balas(201, {"pesan": "Blok berhasil ditambahkan", "block": block_dict})

        elif self.path == "/block":
            block_dict = isi
            induk = CHAIN[-1]
            if block_dict["index"] == induk["index"] + 1 and block_dict["validator_id"] == get_scheduled_validator(block_dict["index"]):
                CHAIN.append(block_dict)
                print(f"[{PORT}] Blok #{block_dict['index']} diterima melalui broadcast jaringan.")
                self._balas(200, {"pesan": "Blok diterima"})
            else:
                self._balas(409, {"pesan": "Blok ditolak / tidak valid"})
        else:
            self._balas(404, {"error": "Endpoint tidak dikenal"})

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Penggunaan: python node.py [PORT] [PEER_LIST (opsional, dipisah koma)]")
        sys.exit(1)
        
    PORT = int(sys.argv[1])
    if len(sys.argv) > 2 and sys.argv[2]:
        PEERS = sys.argv[2].split(",")

    for v_name in VALIDATORS_ORDER:
        salt = b"erdkk_consensus_salt_secure_2026"
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=10000)
        seed = kdf.derive(v_name.encode('utf-8'))
        private_value = (int.from_bytes(seed, byteorder='big') % (SECP256R1_ORDER - 1)) + 1
        priv = ec.derive_private_key(private_value, ec.SECP256R1())
        
        VALIDATOR_PRIV_KEYS[v_name] = priv
        VALIDATOR_PUB_KEYS_HEX[v_name] = get_public_key_hex(priv.public_key())

    CHAIN.append(genesis_block().to_dict())
    print(f"Node Validator Aktif di Port {PORT} dengan Peers: {PEERS}")
    HTTPServer(("0.0.0.0", PORT), NodeHandler).serve_forever()