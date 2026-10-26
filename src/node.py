# node.py
import json
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from core.block import Block
from core.state import get_state_at_chain, compute_state_root
from core.consensus import get_expected_validator, is_chain_valid, VALIDATORS_ORDER, DIFFICULTY
from core.network import broadcast_block, broadcast_tx, resolve_conflicts
from core.crypto_utils import get_public_key_from_hex, get_public_key_hex, verify_signature_ecc

PORT = 0
PEERS = []
CHAIN = []
MEMPOOL = []
NODE_IDENTITY = "VAL_KEMENTAN"

VALIDATOR_PUB_KEYS_HEX = {}
VALIDATOR_PRIV_KEYS = {}
SECP256R1_ORDER = 115792089210356248762697446949407573530086143415290314195533631308867097853951

def genesis_block():
    db_kuota_pemerintah = {
        "7201001": {"nama": "Pak Farmer A", "sisa_kuota_kg": 100},
        "7201002": {"nama": "Pak Farmer B", "sisa_kuota_kg": 100}
    }
    b = Block(0, [db_kuota_pemerintah], "VAL_KEMENTAN", previous_hash="0"*64, nonce=0, chain_context=None)
    b.timestamp = 0
    b.state_root = compute_state_root([b.to_dict_partial()])
    
    sig = VALIDATOR_PRIV_KEYS["VAL_KEMENTAN"].sign(b.compute_hash().encode('utf-8'), ec.ECDSA(hashes.SHA256()))
    b.signature_validator = sig.hex()
    return b

def get_simulated_state_with_mempool():
    temp_chain_sim = list(CHAIN)
    if MEMPOOL:
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
            status_ubah = resolve_conflicts(CHAIN, PEERS, VALIDATOR_PUB_KEYS_HEX)
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
            tx_data = isi.get("transaction", {})
            nik = tx_data.get('nik_petani')
            jumlah_diminta = tx_data.get('jumlah_kg', 0)

            if tx_data in MEMPOOL:
                self._balas(200, {"pesan": "Transaksi sudah ada di mempool", "mempool_size": len(MEMPOOL)})
                return

            simulated_state = get_simulated_state_with_mempool()
            if nik not in simulated_state:
                self._balas(400, {"error": "NIK Petani tidak terdaftar di sistem kuota subsidi!"})
                return
            
            sisa_kuota = simulated_state[nik]['sisa_kuota_kg']
            if jumlah_diminta > sisa_kuota:
                self._balas(400, {"error": f"Ditolak! Kuota tidak cukup di mempool. Sisa: {sisa_kuota} kg"})
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

            MEMPOOL.append(tx_data)
            print(f"[{PORT}] [CP4] Transaksi baru dari NIK {nik} masuk ke Mempool. Total di Mempool: {len(MEMPOOL)}")
            
            broadcast_tx({"transaction": tx_data}, PEERS)
            self._balas(201, {"pesan": "Transaksi berhasil dimasukkan ke Mempool", "mempool_size": len(MEMPOOL)})

        elif self.path == "/mine":
            if not MEMPOOL:
                self._balas(400, {"error": "Mempool kosong, tidak ada transaksi untuk ditambang!"})
                return

            induk = CHAIN[-1]
            next_index = induk["index"] + 1
            
            slot_duration=3
            expected_val = get_expected_validator(slot_duration)
            
            if expected_val != NODE_IDENTITY:
                self._balas(403, {
                    "error": f"Ditolak! Bukan giliran node {NODE_IDENTITY}. Giliran slot saat ini dialihkan ke: {expected_val}"
                    })
                return

            batch_transactions = list(MEMPOOL)
            print(f"\n[{PORT}] [CP5] Block Candidate dibentuk dari {len(batch_transactions)} transaksi di Mempool.")

            prev_block_obj = Block(induk['index'], induk['transactions_data'], induk['validator_id'], induk['previous_hash'], induk['nonce'])
            prev_block_obj.timestamp = induk['timestamp']
            prev_block_obj.merkle_root = induk['merkle_root']
            prev_block_obj.state_root = induk['state_root']
            prev_hash = prev_block_obj.compute_hash()

            block = Block(
                index=next_index,
                transactions_data=batch_transactions,
                validator_id=expected_val,
                previous_hash=prev_hash,
                nonce=0,
                chain_context=CHAIN
            )
            
            print(f"[CP6] Memulai Proof of Work (Difficulty: {DIFFICULTY})...")
            attempts, duration = block.mine_block(DIFFICULTY)
            print(f"[CP6] PoW Selesai! Percobaan nonce: {attempts}")
            print(f"[CP6] Nonce ditemukan: {block.nonce}")
            print(f"[CP6] Hash Block: {block.compute_hash()}")
            print(f"[CP6] Waktu penambangan: {duration:.4f} detik")
            
            sig_val = VALIDATOR_PRIV_KEYS[expected_val].sign(block.compute_hash().encode('utf-8'), ec.ECDSA(hashes.SHA256()))
            block.signature_validator = sig_val.hex()
            
            block_dict = block.to_dict()

            temp_chain = CHAIN + [block_dict]
            if not is_chain_valid(temp_chain, VALIDATOR_PUB_KEYS_HEX):
                print(f"[{PORT}] Blok gagal ditambahkan karena validasi rantai gagal.")
                self._balas(400, {"error": "Blok ditolak oleh aturan konsensus"})
                return

            CHAIN.append(block_dict)
            is_chain_valid(CHAIN, VALIDATOR_PUB_KEYS_HEX)
            
            MEMPOOL.clear()
            
            print(f"[CP7] Blok #{next_index} diterima rantai. Pool dikosongkan. Panjang rantai: {len(CHAIN)}\n")
            
            broadcast_block(block_dict, PORT, PEERS)
            self._balas(201, {"pesan": "Batch blok berhasil ditambang", "block": block_dict})

        elif self.path == "/block":
            block_dict = isi
            temp_incoming_chain = CHAIN + [block_dict]
            if is_chain_valid(temp_incoming_chain, VALIDATOR_PUB_KEYS_HEX):
                CHAIN.append(block_dict)
                incoming_txs = block_dict['transactions_data']
                incoming_ids = {tx['signature_petani'] for tx in incoming_txs}
                MEMPOOL = [tx for tx in MEMPOOL if tx['signature_petani'] not in incoming_ids]
                
                print(f"[{PORT}] [CP10] Blok #{block_dict['index']} diterima via broadcast & Mempool dibersihkan.")
                self._balas(200, {"pesan": "Blok diterima"})
            else:
                print(f"[{PORT}] [CP11] Blok dari peer DITOLAK karena tidak valid!")
                self._balas(409, {"pesan": "Blok ditolak / tidak valid"})
        else:
            self._balas(404, {"error": "Endpoint tidak dikenal"})

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Penggunaan: python node.py [PORT] [PEER_LIST] [NODE_IDENTITY]")
        sys.exit(1)
        
    PORT = int(sys.argv[1])
    if len(sys.argv) > 2 and sys.argv[2]:
        PEERS = sys.argv[2].split(",")
        
    if len(sys.argv) > 3:
        NODE_IDENTITY = sys.argv[3]

    for v_name in VALIDATORS_ORDER:
        salt = b"erdkk_consensus_salt_secure_2026"
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=10000)
        seed = kdf.derive(v_name.encode('utf-8'))
        private_value = (int.from_bytes(seed, byteorder='big') % (SECP256R1_ORDER - 1)) + 1
        priv = ec.derive_private_key(private_value, ec.SECP256R1())
        
        VALIDATOR_PRIV_KEYS[v_name] = priv
        VALIDATOR_PUB_KEYS_HEX[v_name] = get_public_key_hex(priv.public_key())

    CHAIN.append(genesis_block().to_dict())
    print(f"Node Validator Aktif di Port {PORT} (Identitas: {NODE_IDENTITY}) dengan Arsitektur Moduler.")
    HTTPServer(("0.0.0.0", PORT), NodeHandler).serve_forever()