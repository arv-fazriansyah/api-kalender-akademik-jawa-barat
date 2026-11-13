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

    API dilindungi Cloudflare dan menolak IP datacenter asing (403). Karena
    itu script langsung memakai proxy gratis ber-IP Indonesia; koneksi
    langsung hanya dipakai sebagai cadangan terakhir.

Pemakaian:
    python script/scrape-kalender.py
    python script/scrape-kalender.py --proxy http://ip:port
    python script/scrape-kalender.py --cari-proxy        # hanya cari proxy
    python script/scrape-kalender.py --tanpa-proxy       # jangan cari proxy
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests

API_URL = "https://api-webdisdik.jabarprov.go.id/next/api/v1/kalender"
HALAMAN_URL = "https://disdik.jabarprov.go.id/publikasi/kalender-pendidikan"
STORAGE_BASE = "https://storagetikomdik.jabarprov.go.id/website-disdik-v2/"

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
AGENDA_DIR = DATA_DIR / "agenda"
CACHE_DIR = DATA_DIR / ".cache"

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

# Sumber daftar proxy gratis (diutamakan yang ber-IP Indonesia).
PROXY_SOURCES_ID = [
    "https://api.proxyscrape.com/v4/free-proxy-list/get"
    "?request=display_proxies&country=id&protocol=http&proxy_format=ipport&format=text",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/ID/data.txt",
    "https://proxylist.geonode.com/api/proxy-list"
    "?limit=100&page=1&sort_by=lastChecked&sort_type=desc&protocols=http&country=ID",
]
PROXY_SOURCES_GLOBAL = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
]

MAKS_PROXY_DIUJI = 150
WAKER_UJI_PROXY = 24
TIMEOUT_UJI_PROXY = 6


# --------------------------------------------------------------------------- #
# Util
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# Proxy gratis
# --------------------------------------------------------------------------- #
def _normalisasi_proxy(baris: str) -> str | None:
    baris = baris.strip()
    if not baris or baris.startswith("#"):
        return None
    if not baris.startswith(("http://", "https://")):
        baris = "http://" + baris.lstrip("/")
    if not re.match(r"^https?://\d{1,3}(\.\d{1,3}){3}:\d{2,5}$", baris):
        return None
    return baris


def _parse_teks(teks: str) -> Iterable[str]:
    for baris in teks.splitlines():
        proxy = _normalisasi_proxy(baris)
        if proxy:
            yield proxy


def _parse_geonode(teks: str) -> Iterable[str]:
    try:
        data = json.loads(teks).get("data") or []
    except ValueError:
        return []
    hasil = []
    for item in data:
        ip, port = item.get("ip"), item.get("port")
        if ip and port:
            hasil.append(f"http://{ip}:{port}")
    return hasil


def kumpulkan_kandidat_proxy() -> list[str]:
    kandidat: list[str] = []
    for url in PROXY_SOURCES_ID:
        try:
            resp = requests.get(url, timeout=20, headers={"User-Agent": HEADERS["User-Agent"]})
            resp.raise_for_status()
            kandidat.extend(
                _parse_geonode(resp.text) if "geonode" in url else _parse_teks(resp.text)
            )
        except requests.RequestException as exc:
            print(f"  sumber proxy gagal ({url.split('/')[2]}): {exc}")

    print(f"  {len(kandidat)} proxy Indonesia terkumpul")

    if len(kandidat) < 20:
        for url in PROXY_SOURCES_GLOBAL:
            try:
                resp = requests.get(url, timeout=20, headers={"User-Agent": HEADERS["User-Agent"]})
                resp.raise_for_status()
                tambahan = list(_parse_teks(resp.text))[:300]
                kandidat.extend(tambahan)
                print(f"  tambahan {len(tambahan)} proxy global dari {url.split('/')[2]}")
            except requests.RequestException as exc:
                print(f"  sumber proxy gagal ({url.split('/')[2]}): {exc}")

    # buang duplikat, pertahankan urutan
    unik: list[str] = []
    sudah = set()
    for proxy in kandidat:
        if proxy not in sudah:
            sudah.add(proxy)
            unik.append(proxy)
    return unik[:MAKS_PROXY_DIUJI]


def _uji_satu_proxy(proxy: str) -> str | None:
    try:
        resp = requests.get(
            API_URL,
            headers=HEADERS,
            proxies={"http": proxy, "https": proxy},
            timeout=TIMEOUT_UJI_PROXY,
        )
        if resp.status_code != 200:
            return None
        data = resp.json().get("data")
        return proxy if isinstance(data, list) else None
    except (requests.RequestException, ValueError):
        return None


def cari_proxy() -> str | None:
    print("Mencari proxy gratis ber-IP Indonesia...")
    kandidat = kumpulkan_kandidat_proxy()
    if not kandidat:
        return None

    print(f"  menguji {len(kandidat)} proxy (timeout {TIMEOUT_UJI_PROXY}s, {WAKER_UJI_PROXY} paralel)")
    mulai = time.time()
    with ThreadPoolExecutor(max_workers=WAKER_UJI_PROXY) as pool:
        futures = {pool.submit(_uji_satu_proxy, p): p for p in kandidat}
        for future in as_completed(futures):
            hasil = future.result()
            if hasil:
                for lain in futures:
                    lain.cancel()
                print(f"  proxy hidup: {hasil} ({time.time() - mulai:.1f}s)")
                return hasil
    print(f"  tidak ada proxy yang hidup ({time.time() - mulai:.1f}s)")
    return None


# --------------------------------------------------------------------------- #
# Ambil data
# --------------------------------------------------------------------------- #
def _ambil(proxy: str | None) -> list[dict]:
    proxies = {"http": proxy, "https": proxy} if proxy else None
    resp = requests.get(
        API_URL, headers=HEADERS, proxies=proxies, timeout=20 if proxy else TIMEOUT
    )
    resp.raise_for_status()
    payload = resp.json()
    data = payload.get("data")
    return data if isinstance(data, list) else []


def _coba(url_proxy: str | None, label: str, percobaan: int = 2) -> list[dict] | None:
    for i in range(1, percobaan + 1):
        try:
            return _ambil(url_proxy)
        except (requests.RequestException, ValueError) as exc:
            print(f"  {label} percobaan {i}/{percobaan} gagal: {exc}")
            if i < percobaan:
                time.sleep(2)
    return None


def ambil_dari_api(proxy: str | None = None, cari_proxy_otomatis: bool = True) -> tuple[list[dict], str | None]:
    """Kembalikan (data, proxy yang dipakai).

    Urutan: proxy yang diberikan -> proxy gratis hasil pencarian -> koneksi langsung.
    """
    if proxy:
        data = _coba(proxy, f"proxy {proxy}", PERCOBAAN)
        if data is not None:
            return data, proxy
        if not cari_proxy_otomatis:
            raise SystemExit(f"Gagal mengambil API lewat proxy {proxy}")
        print("  proxy yang diberikan gagal, mencari proxy lain")

    if cari_proxy_otomatis:
        # Proxy gratis sering mati, jadi dicari ulang kalau yang didapat tidak jalan.
        for putaran in range(1, 4):
            kandidat = cari_proxy()
            if not kandidat:
                continue
            data = _coba(kandidat, f"proxy {kandidat}")
            if data is not None:
                return data, kandidat
        print("  semua proxy gagal, mencoba koneksi langsung")

    data = _coba(None, "koneksi langsung", PERCOBAAN)
    if data is not None:
        return data, None

    raise SystemExit(
        "Gagal mengambil API, baik lewat proxy maupun langsung.\n"
        "Set PROXY=http://ip:port atau HTTPS_PROXY dengan proxy ber-IP Indonesia."
    )


# --------------------------------------------------------------------------- #
# Susun data
# --------------------------------------------------------------------------- #
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
    """Tulis hanya kalau isi berubah (field diambil_pada diabaikan)."""
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


def simpan_proxy_terakhir(proxy: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / "proxy.txt").write_text(proxy + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape kalender pendidikan Jabar.")
    parser.add_argument("--proxy", help="pakai proxy tertentu, contoh http://1.2.3.4:8080")
    parser.add_argument("--tanpa-proxy", action="store_true", help="jangan cari proxy otomatis")
    parser.add_argument("--cari-proxy", action="store_true", help="hanya cari dan uji proxy, tanpa scrape")
    args = parser.parse_args()

    if args.cari_proxy:
        proxy = args.proxy or os.environ.get("PROXY") or cari_proxy()
        if not proxy:
            print("Tidak ada proxy yang berhasil.")
            return 1
        print(f"Proxy yang bisa dipakai: {proxy}")
        return 0

    diambil_pada = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    berjalan = tahun_ajaran_berjalan()
    awal = int(berjalan.split("-")[0])
    bawaan = [f"{awal}-{awal + 1}", f"{awal - 1}-{awal}"]
    env_filter = os.environ.get("TAHUN_AJARAN", "").strip()
    filter_tahun = [s.strip() for s in env_filter.split(",") if s.strip()] or bawaan

    proxy = args.proxy or os.environ.get("PROXY") or None

    print(f"Mengambil {API_URL}")
    items, proxy_dipakai = ambil_dari_api(
        proxy=proxy, cari_proxy_otomatis=not args.tanpa_proxy
    )
    print(f"API mengembalikan {len(items)} tahun ajaran")
    if proxy_dipakai:
        print(f"  lewat proxy: {proxy_dipakai}")
        simpan_proxy_terakhir(proxy_dipakai)

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
