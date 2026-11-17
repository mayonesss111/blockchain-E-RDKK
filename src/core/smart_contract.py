# src/core/smart_contract.py

class SmartContractERDK:
    """Smart Contract untuk mengatur aturan penyaluran pupuk bersubsidi."""
    
    # Aturan konstanta dalam kontrak
    MAX_TEBUS_PER_TRANSAKSI = 50  # Maksimal 50 kg sekali tebus
    
    # Mapping wilayah NIK (4 digit awal) ke kode wilayah Kios yang diizinkan
    ATURAN_WILAYAH = {
        "7201": "PALU",
        "7202": "DONGGALA"
    }

    @staticmethod
    def validasi_aturan_bisnis(tx_data, current_state):
        """Mengecek apakah transaksi mematuhi seluruh aturan kontrak sebelum masuk mempool/blok."""
        nik = tx_data.get('nik_petani')
        jumlah = tx_data.get('jumlah_kg', 0)
        kios_id = tx_data.get('kios_id', '')

        # 1. Cek apakah NIK terdaftar di state
        if nik not in current_state:
            return False, "Kontrak Ditolak: NIK Petani tidak terdaftar di e-RDKK."

        # 2. Cek batas maksimal penebusan per transaksi
        if jumlah <= 0 or jumlah > SmartContractERDK.MAX_TEBUS_PER_TRANSAKSI:
            return False, f"Kontrak Ditolak: Penebusan harus antara 1 - {SmartContractERDK.MAX_TEBUS_PER_TRANSAKSI} kg."

        # 3. Cek kecukupan sisa kuota
        sisa_kuota = current_state[nik]['sisa_kuota_kg']
        if jumlah > sisa_kuota:
            return False, f"Kontrak Ditolak: Kuota tidak mencukupi (Sisa: {sisa_kuota} kg)."

        # 4. Cek kesesuaian zonasi wilayah NIK dengan Kios (contoh: NIK 7201 wajib di KIOS_PALU_...)
        kode_wilayah_nik = nik[:4]
        wilayah_wajib = SmartContractERDK.ATURAN_WILAYAH.get(kode_wilayah_nik)
        if wilayah_wajib and wilayah_wajib not in kios_id.upper():
            return False, f"Kontrak Ditolak: Petani wilayah {wilayah_wajib} tidak boleh menebus di {kios_id}."

        return True, "Transaksi memenuhi aturan Smart Contract."

    @staticmethod
    def eksekusi_transaksi(tx_data, current_state):
        """Mengubah state ledger jika transaksi valid menurut kontrak."""
        is_valid, pesan = SmartContractERDK.validasi_aturan_bisnis(tx_data, current_state)
        if not is_valid:
            # Jika ada blok palsu dari node nakal yang meloloskan transaksi ilegal, 
            # state tidak akan berubah dan state_root akan otomatis gagal divalidasi!
            return current_state

        nik = tx_data['nik_petani']
        jumlah = tx_data['jumlah_kg']
        
        # Mutasi state resmi
        current_state[nik]['sisa_kuota_kg'] -= jumlah
        return current_state
