# node.py --- Node Validator e-RDKK dengan PoA, Mempool, Merkle Tree Root, State Root, & Broadcast
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
import threading

PORT = 0
PEERS = []
CHAIN = []
MEMPOOL = []  # Antrean transaksi sementara sebelum masuk blok (Batch Mining)

VALIDATORS_ORDER = ["VAL_KEMENTAN", "VAL_PT_PUPUK", "VAL_DINAS_PERTANIAN"]
VALIDATOR_PUB_KEYS_HEX = {}
VALIDATOR_PRIV_KEYS = {}

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

def compute_merkle_root(transactions):
    """Menghitung Merkle Root dari sekumpulan transaksi dalam batch blok."""
    if not transactions:
        return hashlib.sha256(b"").hexdigest()
    
    layer = [hashlib.sha256(json.dumps(tx, sort_keys=True).encode('utf-8')).hexdigest() for tx in transactions]
    
    while len(layer) > 1:
        if len(layer) % 2 != 0:
            layer.append(layer[-1])
        next_layer = []
        for i in range(0, len(layer), 2):
            combined = layer[i] + layer[i+1]
            parent_hash = hashlib.sha256(combined.encode('utf-8')).hexdigest()
            next_layer.append(parent_hash)
        layer = next_layer
    return layer[0]

def get_state_at_chain(chain_subset):
    """Menghitung akumulasi state kuota petani berdasarkan seluruh transaksi di chain."""
    if not chain_subset:
        return {}
    current_state = json.loads(json.dumps(chain_subset[0]['transactions_data'][0]))
    for i in range(1, len(chain_subset)):
        for tx in chain_subset[i]['transactions_data']:
            nik = tx.get('nik_petani')
            jumlah = tx.get('jumlah_kg', 0)
            if nik in current_state:
                current_state[nik]['sisa_kuota_kg'] -= jumlah
    return current_state

def compute_state_root(chain_subset):
    """Menghitung State Root dari kondisi kuota global."""
    state_dict = get_state_at_chain(chain_subset)
    state_str = json.dumps(state_dict, sort_keys=True)
    return hashlib.sha256(state_str.encode('utf-8')).hexdigest()

class Block:
    def __init__(self, index, transactions_data, validator_id, previous_hash=None, nonce=0, chain_context=None):
        self.index = index
        self.timestamp = time.time()
        self.transactions_data = transactions_data  # Berisi list transaksi dalam batch
        self.merkle_root = compute_merkle_root(transactions_data)
        self.validator_id = validator_id
        self.previous_hash = previous_hash
        self.nonce = nonce
        
        self.state_root = "0" * 64
        if chain_context is not None:
            temp_chain = chain_context + [self.to_dict_partial()]
            self.state_root = compute_state_root(temp_chain)
            
        self.signature_validator = None

    def to_dict_partial(self):
        return {
            'index': self.index,
            'timestamp': self.timestamp,
            'transactions_data': self.transactions_data,
            'merkle_root': self.merkle_root,
            'validator_id': self.validator_id,
            'previous_hash': self.previous_hash,
            'nonce': self.nonce,
            'state_root': self.state_root
        }

    def get_block_header(self):
        return json.dumps({
            'index': self.index,
            'timestamp': self.timestamp,
            'merkle_root': self.merkle_root,
            'validator_id': self.validator_id,
            'previous_hash': self.previous_hash,
            'nonce': self.nonce,
            'state_root': self.state_root
        }, sort_keys=True)

    def compute_hash(self):
        payload = self.get_block_header().encode('utf-8')
        return hashlib.sha256(payload).hexdigest()

    def to_dict(self):
        d = self.to_dict_partial()
        d['signature_validator'] = self.signature_validator
        return d

def genesis_block():
    db_kuota_pemerintah = {
        "7201001": {"nama": "Pak Farmer A", "sisa_kuota_kg": 100},
        "7201002": {"nama": "Pak Farmer B", "sisa_kuota_kg": 100}
    }
    b = Block(0, [db_kuota_pemerintah], "VAL_KEMENTAN", previous_hash="0"*64, nonce=0, chain_context=None)
    b.state_root = hashlib.sha256(json.dumps(db_kuota_pemerintah, sort_keys=True).encode('utf-8')).hexdigest()
    
    sig = VALIDATOR_PRIV_KEYS["VAL_KEMENTAN"].sign(b.compute_hash().encode('utf-8'), ec.ECDSA(hashes.SHA256()))
    b.signature_validator = sig.hex()
    return b

def get_scheduled_validator(block_index: int) -> str:
    return VALIDATORS_ORDER[block_index % len(VALIDATORS_ORDER)]

def is_chain_valid(chain):
    if len(chain) == 0:
        return False
    
    for i in range(1, len(chain)):
        curr = chain[i]
        prev = chain[i - 1]
        
        b_obj = Block(curr['index'], curr['transactions_data'], curr['validator_id'], curr['previous_hash'], curr['nonce'])
        b_obj.timestamp = curr['timestamp']
        b_obj.merkle_root = curr['merkle_root']
        b_obj.state_root = curr['state_root']
        
        prev_block_obj = Block(prev['index'], prev['transactions_data'], prev['validator_id'], prev['previous_hash'], prev['nonce'])
        prev_block_obj.timestamp = prev['timestamp']
        prev_block_obj.merkle_root = prev['merkle_root']
        prev_block_obj.state_root = prev['state_root']
        
        if curr['previous_hash'] != prev_block_obj.compute_hash():
            return False
        
        if curr['validator_id'] != get_scheduled_validator(curr['index']):
            return False
            
        computed_merkle = compute_merkle_root(curr['transactions_data'])
        if curr['merkle_root'] != computed_merkle:
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
            
    expected_state_root = compute_state_root(chain)
    if chain[-1]['state_root'] != expected_state_root:
        return False

    return True

def broadcast_block(block_dict):
    def _send():
        for peer in PEERS:
            try:
                data = json.dumps(block_dict).encode("utf-8")
                req = urllib.request.Request(f"http://{peer}/block", data=data, headers={"Content-Type": "application/json"}, method="POST")
                urllib.request.urlopen(req, timeout=3)
            except Exception:
                pass
    threading.Thread(target=_send).start()

def broadcast_tx(tx_dict):
    def _send():
        for peer in PEERS:
            try:
                data = json.dumps(tx_dict).encode("utf-8")
                req = urllib.request.Request(f"http://{peer}/transactions/new", data=data, headers={"Content-Type": "application/json"}, method="POST")
                urllib.request.urlopen(req, timeout=3)
            except Exception:
                pass
    threading.Thread(target=_send).start()

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

def get_simulated_state_with_mempool():
    """Menghitung state berjalan termasuk memperhitungkan transaksi yang masih ada di mempool."""
    temp_chain_sim = list(CHAIN)
    if MEMPOOL:
        # Simulasi blok sementara untuk menguji validitas kuota bertumpuk di mempool
        dummy_block_data = {'index': len(CHAIN), 'transactions_data': list(MEMPOOL), 'validator_id': 'SIM', 'previous_hash': '0', 'nonce': 0}
        temp_chain_sim.append(dummy_block_data)
    return get_state_at_chain(temp_chain_sim)

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
            self._balas(200, {"panjang": len(CHAIN), "chain": CHAIN, "mempool_size": len(MEMPOOL)})
        elif self.path == "/resolve":
            status_ubah = resolve_conflicts()
            self._balas(200, {"rantai_diganti": status_ubah, "panjang": len(CHAIN)})
        elif self.path.startswith("/cek_kuota/"):
            nik = self.path.split("/")[-1]
            state = get_state_at_chain(CHAIN)
            if nik in state:
                self._balas(200, {"nik_petani": nik, "sisa_kuota_kg": state[nik]['sisa_kuota_kg']})
            else:
                self._balas(404, {"error": "NIK Petani tidak ditemukan."})
        else:
            self._balas(404, {"error": "Endpoint tidak dikenal"})

    def do_POST(self):
        global MEMPOOL
        panjang = int(self.headers.get("Content-Length", 0))
        isi = json.loads(self.rfile.read(panjang) or b"{}")

        if self.path == "/transactions/new":
            # Endpoint untuk menerima transaksi baru dan memasukkannya ke Mempool
            tx_data = isi.get("transaction", {})
            nik = tx_data.get('nik_petani')
            jumlah_diminta = tx_data.get('jumlah_kg', 0)

            # Cek apakah transaksi yang sama persis sudah ada di Mempool (mencegah loop broadcast)
            if tx_data in MEMPOOL:
                self._balas(200, {"pesan": "Transaksi sudah ada di mempool", "mempool_size": len(MEMPOOL)})
                return

            # Cek kuota berdasarkan chain + mempool yang sudah antre
            simulated_state = get_simulated_state_with_mempool()
            if nik not in simulated_state:
                self._balas(400, {"error": "NIK Petani tidak terdaftar di sistem kuota subsidi!"})
                return
            
            sisa_kuota = simulated_state[nik]['sisa_kuota_kg']
            if jumlah_diminta > sisa_kuota:
                self._balas(400, {"error": f"Ditolak! Kuota tidak cukup di mempool. Sisa: {sisa_kuota} kg"})
                return

            # Verifikasi tanda tangan ECC petani
            payload_str = f"{nik}:{jumlah_diminta}:{tx_data['kios_id']}:{tx_data['timestamp']}"
            try:
                farmer_pub_key = get_public_key_from_hex(tx_data['public_key_petani_hex'])
                if not verify_signature_ecc(farmer_pub_key, payload_str, tx_data['signature_petani']):
                    self._balas(400, {"error": "Tanda tangan digital petani tidak sah!"})
                    return
            except Exception as e:
                self._balas(400, {"error": f"Internal error: {str(e)}"})
                return

            MEMPOOL.append(tx_data)
            print(f"[{PORT}] Transaksi baru dari NIK {nik} masuk ke Mempool. Total di Mempool: {len(MEMPOOL)}")
            
            # Broadcast transaksi mentah ke peer agar mempool tersinkronisasi
            broadcast_tx({"transaction": tx_data})
            self._balas(201, {"pesan": "Transaksi berhasil dimasukkan ke Mempool", "mempool_size": len(MEMPOOL)})

        elif self.path == "/mine":
            # Endpoint untuk memproses seluruh transaksi di Mempool menjadi 1 Blok baru (Batch Mining)
            if not MEMPOOL:
                self._balas(400, {"error": "Mempool kosong, tidak ada transaksi untuk ditambang!"})
                return

            induk = CHAIN[-1]
            next_index = induk["index"] + 1
            expected_val = get_scheduled_validator(next_index)
            
            if expected_val not in VALIDATOR_PRIV_KEYS:
                self._balas(403, {"error": f"Node ini bukan giliran validator {expected_val}!"})
                return

            # Ambil semua transaksi dari Mempool untuk dibentuk Batch Merkle Tree
            batch_transactions = list(MEMPOOL)

            prev_block_obj = Block(induk['index'], induk['transactions_data'], induk['validator_id'], induk['previous_hash'], induk['nonce'])
            prev_block_obj.timestamp = induk['timestamp']
            prev_block_obj.merkle_root = induk['merkle_root']
            prev_block_obj.state_root = induk['state_root']
            prev_hash = prev_block_obj.compute_hash()

            # Buat blok baru dengan sekumpulan transaksi batch
            block = Block(
                index=next_index,
                transactions_data=batch_transactions,
                validator_id=expected_val,
                previous_hash=prev_hash,
                nonce=next_index,
                chain_context=CHAIN
            )
            
            sig_val = VALIDATOR_PRIV_KEYS[expected_val].sign(block.compute_hash().encode('utf-8'), ec.ECDSA(hashes.SHA256()))
            block.signature_validator = sig_val.hex()
            
            block_dict = block.to_dict()
            CHAIN.append(block_dict)
            
            # Kosongkan mempool setelah berhasil ditambang
            MEMPOOL.clear()
            
            print(f"[{PORT}] Blok Batched #{next_index} berhasil ditambang oleh {expected_val} memuat {len(batch_transactions)} transaksi (Merkle Root & State Root secured)")
            
            broadcast_block(block_dict)
            self._balas(201, {"pesan": "Batch blok berhasil ditambang", "block": block_dict})

        elif self.path == "/block":
            block_dict = isi
            temp_incoming_chain = CHAIN + [block_dict]
            if is_chain_valid(temp_incoming_chain):
                CHAIN.append(block_dict)
                # Bersihkan transaksi di mempool lokal yang sudah masuk ke blok dari node lain
                incoming_txs = block_dict['transactions_data']
                
                MEMPOOL = [tx for tx in MEMPOOL if tx not in incoming_txs]
                
                print(f"[{PORT}] Blok #{block_dict['index']} diterima via broadcast & Mempool dibersihkan.")
                self._balas(200, {"pesan": "Blok diterima"})
            else:
                self._balas(409, {"pesan": "Blok ditolak / tidak valid"})
        else:
            self._balas(404, {"error": "Endpoint tidak dikenal"})

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Penggunaan: python node.py [PORT] [PEER_LIST]")
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
    print(f"Node Validator Aktif di Port {PORT} dengan Mempool & Merkle Batch Ready.")
    HTTPServer(("0.0.0.0", PORT), NodeHandler).serve_forever()