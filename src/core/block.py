# block.py
import hashlib
import json
import time

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

class Block:
    def __init__(self, index, transactions_data, validator_id, previous_hash=None, nonce=0, chain_context=None):
        self.index = index
        self.timestamp = time.time()
        self.transactions_data = transactions_data
        self.merkle_root = compute_merkle_root(transactions_data)
        self.validator_id = validator_id
        self.previous_hash = previous_hash
        self.nonce = nonce
        
        self.state_root = "0" * 64
        if chain_context is not None:
            from core.state import compute_state_root
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

    def mine_block(self, difficulty):
        target = '0' * difficulty
        attempts = 0
        start_time = time.time()
        
        while self.compute_hash()[:difficulty] != target:
            self.nonce += 1
            attempts += 1
            
        end_time = time.time()
        return attempts, end_time - start_time

    def to_dict(self):
        d = self.to_dict_partial()
        d['signature_validator'] = self.signature_validator
        return d