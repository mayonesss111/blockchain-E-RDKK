from core.block import compute_merkle_root

A = {"nik_petani": "7201001", "jumlah_kg": 30, "kios_id": "KIOS_PALU_01", "timestamp": 1.0}
B = {"nik_petani": "7201001", "jumlah_kg": 20, "kios_id": "KIOS_PALU_01", "timestamp": 2.0}
C = {"nik_petani": "7201001", "jumlah_kg": 40, "kios_id": "KIOS_PALU_01", "timestamp": 3.0}

r1 = compute_merkle_root([A, B, C])
r2 = compute_merkle_root([A, B, C, C])

print("root [A,B,C]   :", r1)
print("root [A,B,C,C] :", r2)
print("IDENTIK?       :", r1 == r2)