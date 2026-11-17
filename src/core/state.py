# state.py
import json
import hashlib
from core.smart_contract import SmartContractERDK

def get_state_at_chain(chain_subset):
    """Menghitung akumulasi state kuota petani menggunakan smart contract."""
    if not chain_subset:
        return {}
    current_state = json.loads(json.dumps(chain_subset[0]['transactions_data'][0]))
    for i in range(1, len(chain_subset)):
        for tx in chain_subset[i]['transactions_data']:
            # Eksekusi setiap transaksi melalui Smart Contract
            current_state = SmartContractERDK.eksekusi_transaksi(tx, current_state)

    return current_state

def compute_state_root(chain_subset):
    """Menghitung State Root dari kondisi kuota global."""
    state_dict = get_state_at_chain(chain_subset)
    state_str = json.dumps(state_dict, sort_keys=True)
    return hashlib.sha256(state_str.encode('utf-8')).hexdigest()