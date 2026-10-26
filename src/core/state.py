# state.py
import json
import hashlib

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