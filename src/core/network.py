# network.py
import json
import urllib.request
import threading

def broadcast_block(block_dict, port, peers):
    def _send():
        for peer in peers:
            try:
                data = json.dumps(block_dict).encode("utf-8")
                req = urllib.request.Request(f"http://{peer}/block", data=data, headers={"Content-Type": "application/json"}, method="POST")
                urllib.request.urlopen(req, timeout=3)
                print(f"[{port}] [CP10] Berhasil broadcast Block #{block_dict['index']} ke peer {peer}")
            except Exception as e:
                print(f"[{port}] [CP10] Gagal broadcast ke peer {peer}: {e}")
    threading.Thread(target=_send).start()

def broadcast_tx(tx_dict, peers):
    def _send():
        for peer in peers:
            try:
                data = json.dumps(tx_dict).encode("utf-8")
                req = urllib.request.Request(f"http://{peer}/transactions/new", data=data, headers={"Content-Type": "application/json"}, method="POST")
                urllib.request.urlopen(req, timeout=3)
            except Exception:
                pass
    threading.Thread(target=_send).start()

def resolve_conflicts(chain, peers, validator_pub_keys_hex):
    from consensus import is_chain_valid
    terpanjang = chain
    berubah = False
    for peer in peers:
        try:
            req = urllib.request.Request(f"http://{peer}/chain")
            with urllib.request.urlopen(req, timeout=3) as res:
                kandidat = json.loads(res.read().decode("utf-8"))["chain"]
                if len(kandidat) >= len(terpanjang) and is_chain_valid(kandidat, validator_pub_keys_hex):
                    terpanjang = kandidat
                    berubah = True
        except Exception:
            pass
    if berubah:
        chain[:] = terpanjang
        return True
    return False