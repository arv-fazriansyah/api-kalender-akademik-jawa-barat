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
  scrape-kalender.py       scraper (satu-satunya script)
  run-daily.ps1            scrape + commit + push (Windows)
  register-task.ps1        daftarkan jadwal harian 01.00
.github/workflows/
  scrape-kalender.yml      jadwal harian 01.00 WIB
```

---

## Cara kerja

1. `script/scrape-kalender.py` memanggil API publik Disdik Jawa Barat.
2. Kalau request langsung ditolak (HTTP 403 dari Cloudflare), script otomatis mengambil daftar proxy gratis ber-IP Indonesia, mengujinya paralel, lalu memakai yang hidup.
3. Metadata (id, tahun ajaran, tautan poster) digabungkan dengan agenda kurasi di `data/agenda/`.
4. Hasil ditulis ke `data/kalender.json` dan `data/<tahun>-<tahun>.json`. File hanya ditulis ulang kalau isinya berubah, jadi tidak ada commit kosong.

Menjalankan manual:

```bash
pip install requests
python script/scrape-kalender.py

# cari proxy Indonesia yang hidup saja
python script/scrape-kalender.py --cari-proxy

# pakai proxy tertentu
python script/scrape-kalender.py --proxy http://1.2.3.4:8080

# paksa tanpa proxy (gagal kalau IP diblokir)
python script/scrape-kalender.py --tanpa-proxy

# hanya tahun ajaran tertentu
TAHUN_AJARAN=2025-2026,2026-2027 python script/scrape-kalender.py
```

Memasang jadwal harian di Windows (opsional, cadangan kalau proxy gratis sedang mati):

```powershell
powershell -ExecutionPolicy Bypass -File script\register-task.ps1
Start-ScheduledTask -TaskName "Kalender Jabar Scrape"   # uji sekali
```

Log tersimpan di `logs/scrape-YYYY-MM.log`.

### Soal Cloudflare

API Disdik dilindungi Cloudflare dan menolak permintaan dari IP datacenter luar
negeri, termasuk runner GitHub Actions (selalu **HTTP 403**). Request dari koneksi
rumah di Indonesia berhasil.

Karena itu script memakai jalur cadangan proxy gratis ber-IP Indonesia
(proxyscrape, proxifly, geonode). Kalau punya proxy tetap, set secret `PROXY`
atau `HTTPS_PROXY` — nilainya dipakai lebih dulu sebelum pencarian otomatis.

Catatan: proxy gratis bisa mati kapan saja. Kalau workflow gagal, jalankan
Task Scheduler lokal atau isi `PROXY` dengan proxy langganan.


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
