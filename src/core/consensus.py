from core.block import Block, compute_merkle_root
from core.state import compute_state_root
from core.crypto_utils import get_public_key_from_hex
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
import time

VALIDATORS_ORDER = ["VAL_KEMENTAN", "VAL_PT_PUPUK", "VAL_DINAS_PERTANIAN"]
DIFFICULTY = 3

def get_expected_validator(next_index, prev_timestamp, slot_duration):
    elapsed = time.time() - prev_timestamp
    turn_offset = int(elapsed // slot_duration)
    # Urutan bergeser secara alami dari indeks dasar penanda blok sebelumnya
    validator_index = (next_index + turn_offset) % len(VALIDATORS_ORDER)
    return VALIDATORS_ORDER[validator_index]

def get_validator_for_block(curr, prev, slot_duration):
    elapsed = curr['timestamp'] - prev['timestamp']
    turn_offset = max(0, int(elapsed // slot_duration))
    # PERBAIKAN: Rumus disinkronkan dengan penentuan expected_validator utama
    validator_index = (curr['index'] + turn_offset) % len(VALIDATORS_ORDER)
    return VALIDATORS_ORDER[validator_index]

def is_chain_valid(chain, validator_pub_keys_hex, slot_duration):
    if len(chain) == 0:
        return False
    
    # Hitung batas minimal jeda giliran berdasarkan jumlah validator aktif
    LIMIT_JEDA = (len(VALIDATORS_ORDER) // 2) + 1

    for i in range(1, len(chain)):
        curr = chain[i]
        prev = chain[i - 1]

        start_check = max(0, i - LIMIT_JEDA)
        for j in range(start_check, i):
            if chain[j]['validator_id'] == curr['validator_id']:
                print(f"[CP11] Block #{curr['index']} DITOLAK: Validator {curr['validator_id']} mencoba menerbitkan blok terlalu cepat / berturut-turut!")
                return False
        
        # PERBAIKAN: Masukkan timestamp historis langsung ke konstruktor agar nilai hash konsisten
        b_obj = Block(
            index=curr['index'], 
            transactions_data=curr['transactions_data'], 
            validator_id=curr['validator_id'], 
            previous_hash=curr['previous_hash'], 
            nonce=curr['nonce'],
            timestamp=curr['timestamp']
        )
        b_obj.merkle_root = curr['merkle_root']
        b_obj.state_root = curr['state_root']
        
        prev_block_obj = Block(
            index=prev['index'], 
            transactions_data=prev['transactions_data'], 
            validator_id=prev['validator_id'], 
            previous_hash=prev['previous_hash'], 
            nonce=prev['nonce'],
            timestamp=prev['timestamp']
        )
        prev_block_obj.merkle_root = prev['merkle_root']
        prev_block_obj.state_root = prev['state_root']
        
        if curr['previous_hash'] != prev_block_obj.compute_hash():
            print(f"[CP11] Block #{curr['index']} DITOLAK: Previous hash tidak cocok!")
            return False
        
        expected_val = get_validator_for_block(curr, prev, slot_duration)
        if curr['validator_id'] != expected_val:
            print(f"[CP11] Block #{curr['index']} DITOLAK: Validator {curr['validator_id']} tidak sah pada slot ini!")
            return False
            
        if curr['merkle_root'] != compute_merkle_root(curr['transactions_data']):
            print(f"[CP11] Block #{curr['index']} DITOLAK: Merkle Root tidak valid!")
            return False

        if b_obj.compute_hash()[:DIFFICULTY] != '0' * DIFFICULTY:
            print(f"[CP11] Block #{curr['index']} DITOLAK: Proof of Work tidak valid!")
            return False

        val_pub_hex = validator_pub_keys_hex.get(curr['validator_id'])
        if not val_pub_hex:
            return False
            
        val_pub_key = get_public_key_from_hex(val_pub_hex)
        sig_val = bytes.fromhex(curr['signature_validator'])
        try:
            val_pub_key.verify(sig_val, b_obj.compute_hash().encode('utf-8'), ec.ECDSA(hashes.SHA256()))
        except Exception:
            print(f"[CP11] Block #{curr['index']} DITOLAK: Tanda tangan validator tidak sah!")
            return False
            
    if chain[-1]['state_root'] != compute_state_root(chain):
        print("[CP11] Validasi Gagal: State root akhir tidak cocok!")
        return False

    print("[CP8] Validasi Rantai: VALID (Semua hash dan previous_hash cocok).")
    return True
