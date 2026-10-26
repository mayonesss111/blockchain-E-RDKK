# network.py
import json
import urllib.request
import threading
import time

from core.consensus import is_chain_valid

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

def resolve_conflicts(chain, peers, validator_pub_keys_hex, slot_duration):
    terpanjang = chain
    berubah = False
    for peer in peers:
        try:
            req = urllib.request.Request(f"http://{peer}/chain")
            with urllib.request.urlopen(req, timeout=3) as res:
                kandidat = json.loads(res.read().decode("utf-8"))["chain"]
                if len(kandidat) >= len(terpanjang) and is_chain_valid(kandidat, validator_pub_keys_hex, slot_duration):
                    terpanjang = kandidat
                    berubah = True
        except Exception:
            pass
    if berubah:
        chain[:] = terpanjang
        print(f"[SYSTEM] Rantai berhasil diperbarui otomatis ke panjang baru: {len(chain)} blok.")
        return True
    return False

def sync_mempool(local_mempool, peers):
    """Menarik transaksi dari mempool peer yang aktif jika mempool lokal kosong."""
    for peer in peers:
        try:
            req = urllib.request.Request(f"http://{peer}/mempool")
            with urllib.request.urlopen(req, timeout=3) as res:
                data = json.loads(res.read().decode("utf-8"))
                peer_mempool = data.get("mempool", [])
                for tx in peer_mempool:
                    if tx not in local_mempool:
                        local_mempool.append(tx)
            if local_mempool:
                break
        except Exception:
            pass

def background_sync_loop(chain, mempool, peers, pub_keys, slot_duration):
    """Loop otomatis di latar belakang untuk menjaga chain dan mempool tetap update."""
    def _sync_loop():
        print("[SYSTEM] Background Sync Thread...")
        while True:
            try:
                if peers:
                    #1 Otomatis tarik transaksi dari mempool node tetangga jika lokal tertinggal
                    sync_mempool(mempool, peers)

                    #2 Otomatis cek apakah ada blok baru di node tetangga 
                    resolve_conflicts(chain, peers, pub_keys, slot_duration)

            except Exception as e:
                print(f"[SYSTEM] Gagal melakukan background sync: {e}")

            #Lakukan pengecekan otomatis setiap 5 detik
            time.sleep(5)
    
    threading.Thread(target=_sync_loop, daemon=True).start()
    