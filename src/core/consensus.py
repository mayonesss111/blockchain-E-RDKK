# consensus.py
from core.block import Block, compute_merkle_root
from core.state import compute_state_root
from core.crypto_utils import get_public_key_from_hex
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
import time

VALIDATORS_ORDER = ["VAL_KEMENTAN", "VAL_PT_PUPUK", "VAL_DINAS_PERTANIAN"]
DIFFICULTY = 3

def get_expected_validator(slot_duration=3):
    """
    Menghitung siapa validator yang sah berdasarkan waktu (timestamp) blok dicetak,
    sehingga fungsi validasi masa lalu tahu apakah sebuah skip-turn sah atau ilegal.
    """
    current_slot = int(time.time() // slot_duration)
    validator_index = current_slot % len(VALIDATORS_ORDER)
    return VALIDATORS_ORDER[validator_index]

def get_validator_at_time(block_timestamp, slot_duration=3):
    """Menghitung validator sah berdasarkan timestamp historis saat blok dicetak."""
    block_slot = int(block_timestamp // slot_duration)
    validator_index = block_slot % len(VALIDATORS_ORDER)
    return VALIDATORS_ORDER[validator_index]

def is_chain_valid(chain, validator_pub_keys_hex):
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
        
        # Validasi kepenulisan blok berdasarkan timestamp historis blok tersebut
        expected_val = get_validator_at_time(curr['timestamp'])

        if curr['validator_id'] != expected_val:
            print(f"[CP11] Block #{curr['index']} DITOLAK: Validator {curr['validator_id']} tidak sah pada slot waktu tersebut!")
            return False
            
        computed_merkle = compute_merkle_root(curr['transactions_data'])
        if curr['merkle_root'] != computed_merkle:
            return False

        block_hash = b_obj.compute_hash()
        if block_hash[:DIFFICULTY] != '0' * DIFFICULTY:
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
            return False
            
    expected_state_root = compute_state_root(chain)
    if chain[-1]['state_root'] != expected_state_root:
        return False

    print("[CP8] Validasi Rantai: VALID (Semua hash dan previous_hash cocok).")
    return True