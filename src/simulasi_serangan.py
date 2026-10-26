import urllib.request
import json
import urllib.error

def simulate_cp9_manipulation():
    print("\n=== [CP9] SIMULASI MANIPULASI DATA BLOCK ===")
    # 1. Ambil rantai dari Node 1
    req = urllib.request.Request("http://localhost:5001/chain")
    with urllib.request.urlopen(req) as res:
        data = json.loads(res.read().decode("utf-8"))
        chain = data["chain"]

    print(f"Rantai saat ini: {len(chain)} blok.")
    
    # 2. Manipulasi data transaksi di Blok #1 (ubah 40 kg jadi 9999 kg)
    if len(chain) > 1:
        target_block = chain[1]
        original_amount = target_block['transactions_data'][0]['jumlah_kg']
        target_block['transactions_data'][0]['jumlah_kg'] = 9999 
        
        print(f"Mengubah data Blok #1: {original_amount} kg menjadi 9999 kg...")
        
        # 3. Coba kirim blok yang sudah dimanipulasi ke Node 2
        payload = json.dumps(target_block).encode("utf-8")
        req = urllib.request.Request("http://localhost:5002/block", data=payload, headers={"Content-Type": "application/json"}, method="POST")
        
        try:
            with urllib.request.urlopen(req) as res:
                print("Respon Node:", res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            print(f"[CP9] SUKSES! Node 2 menolak blok yang dimanipulasi.")
            print(f"Status HTTP: {e.code} - {e.reason}")

def simulate_cp11_invalid_pow():
    print("\n=== [CP11] SIMULASI PENOLAKAN BLOCK TANPA PROOF OF WORK ===")
    # 1. Ambil rantai dari Node 1
    req = urllib.request.Request("http://localhost:5001/chain")
    with urllib.request.urlopen(req) as res:
        data = json.loads(res.read().decode("utf-8"))
        chain = data["chain"]

    # 2. Buat block palsu (hash tidak diawali '000')
    fake_block = chain[-1].copy()
    fake_block['index'] += 1
    fake_block['nonce'] = 0 # Nonce curang (tidak ditambang)
    fake_block['transactions_data'] = [{"nik_petani": "7201001", "jumlah_kg": 1, "kios_id": "PALSU", "timestamp": 123}]
    
    print("Mengirim Block Palsu ke Node 2...")
    payload = json.dumps(fake_block).encode("utf-8")
    req = urllib.request.Request("http://localhost:5002/block", data=payload, headers={"Content-Type": "application/json"}, method="POST")
    
    try:
        with urllib.request.urlopen(req) as res:
            print("Respon Node:", res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"[CP11] SUKSES! Node 2 menolak block karena Proof of Work tidak valid.")
        print(f"Status HTTP: {e.code} - {e.reason}")

if __name__ == "__main__":
    simulate_cp9_manipulation()
    simulate_cp11_invalid_pow()