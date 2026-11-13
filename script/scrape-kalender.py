"""
Scraper Kalender Pendidikan Dinas Pendidikan Provinsi Jawa Barat.

Halaman sumber : https://disdik.jabarprov.go.id/publikasi/kalender-pendidikan
API sumber     : https://api-webdisdik.jabarprov.go.id/next/api/v1/kalender

Output (folder /data):
    data/kalender.json          -> indeks semua tahun ajaran
    data/<tahun>-<tahun>.json   -> satu file per tahun ajaran (metadata + agenda)

Catatan:
    API hanya menyediakan tautan gambar poster, bukan teks tanggal. Agenda
    kurasi disimpan di data/agenda/<slug>.json dan digabungkan saat scrape.
    Tahun ajaran berjalan otomatis dibuat sebagai placeholder berstatus
    "belum_dipublikasikan" sampai API menyediakannya. Gambar tidak diunduh.

    Secara bawaan hanya tahun ajaran berjalan dan tahun sebelumnya yang
    ditulis. Set TAHUN_AJARAN untuk memilih sendiri, mis. "2023-2024".

Pemakaian:
    python script/scrape-kalender.py
    TAHUN_AJARAN=2025-2026,2026-2027 python script/scrape-kalender.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

API_URL = "https://api-webdisdik.jabarprov.go.id/next/api/v1/kalender"
HALAMAN_URL = "https://disdik.jabarprov.go.id/publikasi/kalender-pendidikan"
STORAGE_BASE = "https://storagetikomdik.jabarprov.go.id/website-disdik-v2/"

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
AGENDA_DIR = DATA_DIR / "agenda"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    "Referer": HALAMAN_URL,
    "Origin": "https://disdik.jabarprov.go.id",
}
TIMEOUT = 30
PERCOBAAN = 3


def slugify_tahun_ajaran(value: str) -> str | None:
    """'2025 -2026' atau '2025/2026' -> '2025-2026'."""
    match = re.search(r"(\d{4})\D*(\d{4})", str(value or ""))
    return f"{match.group(1)}-{match.group(2)}" if match else None


def label_tahun_ajaran(slug: str) -> str:
    return slug.replace("-", "/")


def tahun_ajaran_berjalan(tanggal: datetime | None = None) -> str:
    tanggal = tanggal or datetime.now(timezone.utc)
    mulai = tanggal.year if tanggal.month >= 7 else tanggal.year - 1
    return f"{mulai}-{mulai + 1}"


def absolutize(url: str | None) -> str | None:
    if not url:
        return None
    if re.match(r"^https?://", url, re.I):
        return url
    return STORAGE_BASE + url.lstrip("/")


def ambil_dari_api() -> list[dict]:
    terakhir = None
    for percobaan in range(1, PERCOBAAN + 1):
        try:
            resp = requests.get(API_URL, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            payload = resp.json()
            data = payload.get("data")
            return data if isinstance(data, list) else []
        except (requests.RequestException, ValueError) as exc:
            terakhir = exc
            print(f"  percobaan {percobaan}/{PERCOBAAN} gagal: {exc}")
            if percobaan < PERCOBAAN:
                time.sleep(5 * percobaan)
    raise SystemExit(f"Gagal mengambil API: {terakhir}")


def baca_agenda_kurasi(slug: str) -> dict:
    file = AGENDA_DIR / f"{slug}.json"
    if not file.exists():
        return {"agenda": [], "penilaian_akhir": [], "catatan": []}
    isi = json.loads(file.read_text(encoding="utf-8"))
    return {
        "agenda": isi.get("agenda", []),
        "penilaian_akhir": isi.get("penilaian_akhir", []),
        "catatan": isi.get("catatan", []),
    }


def bangun_entri(item: dict, diambil_pada: str) -> dict | None:
    slug = slugify_tahun_ajaran(item.get("tahun_ajaran"))
    if not slug:
        return None

    dokumen = []
    for key, halaman in (("image_1", 1), ("image_2", 2)):
        url = absolutize(item.get(key))
        if url:
            dokumen.append({"halaman": halaman, "url": url})

    kurasi = baca_agenda_kurasi(slug)
    return {
        "tahun_ajaran": label_tahun_ajaran(slug),
        "slug": slug,
        "status": "tersedia" if dokumen else "belum_dipublikasikan",
        "sumber": {
            "halaman": HALAMAN_URL,
            "api": API_URL,
            "id": item.get("id"),
            "pembaruan_terakhir": item.get("updated_at"),
            "dibuat": item.get("created_at"),
        },
        "dokumen": dokumen,
        "agenda": kurasi["agenda"],
        "penilaian_akhir": kurasi["penilaian_akhir"],
        "catatan": kurasi["catatan"],
        "diambil_pada": diambil_pada,
    }


def entri_kosong(slug: str, diambil_pada: str) -> dict:
    return {
        "tahun_ajaran": label_tahun_ajaran(slug),
        "slug": slug,
        "status": "belum_dipublikasikan",
        "sumber": {
            "halaman": HALAMAN_URL,
            "api": API_URL,
            "id": None,
            "pembaruan_terakhir": None,
            "dibuat": None,
        },
        "dokumen": [],
        "agenda": [],
        "penilaian_akhir": [],
        "catatan": ["Belum ada data kalender untuk tahun ajaran ini di API."],
        "diambil_pada": diambil_pada,
    }


def tulis_json(file: Path, data: dict) -> None:
    file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def tulis_json_jika_berubah(file: Path, data: dict) -> bool:
    """Tulis hanya kalau isi berubah (field diambil_pada diabaikan).

    Tujuannya agar commit harian tidak dibuat saat data memang belum berubah.
    """
    if file.exists():
        try:
            lama = json.loads(file.read_text(encoding="utf-8"))
            lama_isi = {k: v for k, v in lama.items() if k != "diambil_pada"}
            baru_isi = {k: v for k, v in data.items() if k != "diambil_pada"}
            if lama_isi == baru_isi:
                return False
        except ValueError:
            pass
    tulis_json(file, data)
    return True


def main() -> int:
    diambil_pada = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    berjalan = tahun_ajaran_berjalan()
    awal = int(berjalan.split("-")[0])
    bawaan = [f"{awal}-{awal + 1}", f"{awal - 1}-{awal}"]
    env_filter = os.environ.get("TAHUN_AJARAN", "").strip()
    filter_tahun = [s.strip() for s in env_filter.split(",") if s.strip()] or bawaan

    print(f"Mengambil {API_URL}")
    items = ambil_dari_api()
    print(f"API mengembalikan {len(items)} tahun ajaran")

    entri: dict[str, dict] = {}
    for item in items:
        data = bangun_entri(item, diambil_pada)
        if data:
            entri[data["slug"]] = data

    entri.setdefault(berjalan, entri_kosong(berjalan, diambil_pada))

    urut = [entri[slug] for slug in sorted(entri, reverse=True) if slug in filter_tahun]
    if not urut:
        raise SystemExit(f"Tidak ada tahun ajaran yang cocok: {', '.join(filter_tahun)}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    jumlah_berubah = 0
    for data in urut:
        file = DATA_DIR / f"{data['slug']}.json"
        berubah = tulis_json_jika_berubah(file, data)
        jumlah_berubah += int(berubah)
        print(
            f"  {file.name}  ({data['status']}, {len(data['agenda'])} agenda, "
            f"{len(data['dokumen'])} dokumen, {'diperbarui' if berubah else 'tidak berubah'})"
        )

    indeks = {
        "sumber": {"halaman": HALAMAN_URL, "api": API_URL},
        "diambil_pada": diambil_pada,
        "jumlah": len(urut),
        "tahun_ajaran": [
            {
                "slug": e["slug"],
                "tahun_ajaran": e["tahun_ajaran"],
                "status": e["status"],
                "file": f"data/{e['slug']}.json",
                "jumlah_agenda": len(e["agenda"]),
                "jumlah_dokumen": len(e["dokumen"]),
                "pembaruan_terakhir": e["sumber"]["pembaruan_terakhir"],
            }
            for e in urut
        ],
    }
    tulis_json_jika_berubah(DATA_DIR / "kalender.json", indeks)
    print(f"  kalender.json (indeks, {jumlah_berubah} file tahun ajaran diperbarui)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
