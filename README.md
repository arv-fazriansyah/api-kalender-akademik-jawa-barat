# API Kalender Akademik Jawa Barat

Data **Kalender Pendidikan Dinas Pendidikan Provinsi Jawa Barat** dalam bentuk JSON statis.
Diperbarui otomatis setiap hari pukul **01.00 WIB** langsung dari sumber resmi.

---

## Endpoint

Base URL:

```
https://raw.githubusercontent.com/arv-fazriansyah/api-kalender-akademik-jawa-barat/main/data/
```

| File | Keterangan |
| --- | --- |
| `kalender.json` | Indeks semua tahun ajaran yang tersedia |
| `2025-2026.json` | Kalender tahun ajaran 2025-2026 (lengkap) |
| `2026-2027.json` | Tahun ajaran 2026-2027 (placeholder, menunggu publikasi) |

Contoh:

```bash
curl https://raw.githubusercontent.com/arv-fazriansyah/api-kalender-akademik-jawa-barat/main/data/2025-2026.json
```

```js
const res = await fetch(
  'https://raw.githubusercontent.com/arv-fazriansyah/api-kalender-akademik-jawa-barat/main/data/kalender.json'
);
const indeks = await res.json();
console.log(indeks.tahun_ajaran);
```

---

## Skema

### `kalender.json`

```json
{
  "sumber": { "halaman": "...", "api": "..." },
  "diambil_pada": "2026-11-13T04:49:28Z",
  "jumlah": 2,
  "tahun_ajaran": [
    {
      "slug": "2026-2027",
      "tahun_ajaran": "2026/2027",
      "status": "belum_dipublikasikan",
      "file": "data/2026-2027.json",
      "jumlah_agenda": 0,
      "jumlah_dokumen": 0,
      "pembaruan_terakhir": null
    }
  ]
}
```

### `data/<tahun>-<tahun>.json`

| Field | Tipe | Keterangan |
| --- | --- | --- |
| `tahun_ajaran` | string | Format `YYYY/YYYY` |
| `slug` | string | Nama file, contoh `2025-2026` |
| `status` | string | `tersedia` atau `belum_dipublikasikan` |
| `sumber` | object | Halaman, API, id, `pembaruan_terakhir`, `dibuat` |
| `dokumen` | array | `{ halaman, url }` poster resmi (JPG/JPEG) |
| `agenda` | array | Daftar kegiatan dan libur (lihat di bawah) |
| `penilaian_akhir` | array | Jadwal sumatif akhir jenjang dan tes kompetensi akademik |
| `catatan` | array | Catatan tambahan per tahun ajaran |
| `diambil_pada` | string | Waktu scrape (ISO 8601, UTC) |

Setiap item `agenda`:

```json
{
  "semester": 1,
  "mulai": "2025-07-14",
  "selesai": "2025-07-16",
  "kategori": "kegiatan",
  "agenda": "Pengenalan Lingkungan Sekolah",
  "catatan": "opsional"
}
```

Nilai `kategori`: `libur`, `kegiatan`, `asesmen`, `rapor`, `kelulusan`, `peringatan`.

---

## Struktur repo

```
data/
  kalender.json            indeks semua tahun ajaran
  2025-2026.json           detail per tahun ajaran
  2026-2027.json
  agenda/
    2025-2026.json         agenda kurasi (sumber penggabungan)
script/
  scrape-kalender.py       scraper
.github/workflows/
  scrape-kalender.yml      penjadwal harian
```

---

## Cara kerja

1. `script/scrape-kalender.py` memanggil API publik Disdik Jawa Barat.
2. Metadata (id, tahun ajaran, tautan poster) digabungkan dengan agenda kurasi di `data/agenda/`.
3. Hasil ditulis ke `data/kalender.json` dan `data/<tahun>-<tahun>.json`.
4. GitHub Actions menjalankan proses ini setiap hari dan meng-commit perubahan.

Menjalankan manual:

```bash
pip install requests
python script/scrape-kalender.py

# hanya tahun ajaran tertentu
TAHUN_AJARAN=2025-2026,2026-2027 python script/scrape-kalender.py
```

---

## Keterbatasan

- API resmi hanya menyediakan **gambar poster**, bukan teks tanggal. Karena itu `agenda` dan `penilaian_akhir` diekstraksi manual dari poster dan tidak berubah otomatis. Perubahan tanggal pada poster baru harus diperbarui di `data/agenda/<tahun>-<tahun>.json`.
- Tahun ajaran yang belum terbit tetap dibuat sebagai placeholder berstatus `belum_dipublikasikan`.
- Semua tanggal bersifat **prakiraan** sesuai poster resmi; libur keagamaan menunggu keputusan pemerintah.
- Gambar poster tidak disimpan di repo, hanya tautannya.

---

## Sumber

- Halaman: <https://disdik.jabarprov.go.id/publikasi/kalender-pendidikan>
- API: <https://api-webdisdik.jabarprov.go.id/next/api/v1/kalender>

Proyek ini bukan layanan resmi Dinas Pendidikan Provinsi Jawa Barat. Selalu cocokkan dengan dokumen resmi sebelum digunakan untuk keputusan akademik.
