"""
Ambil JSON kalender pendidikan lewat browser sungguhan (Playwright).

Dipakai sebagai jalan tengah saat request HTTP biasa diblokir Cloudflare
(HTTP 403). Browser menjalankan JavaScript halaman sehingga challenge
Cloudflare bisa selesai, lalu endpoint API dipanggil dari dalam konteks
halaman yang sudah punya cookie clearance.

Hasil disimpan sebagai JSON mentah, lalu diolah oleh scrape-kalender.py
(otomatis memakai file ini kalau request langsung gagal).

Pemakaian:
    python script/fetch-browser.py
    python script/fetch-browser.py --out data/.cache/api-kalender.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

HALAMAN_URL = "https://disdik.jabarprov.go.id/publikasi/kalender-pendidikan"
API_URL = "https://api-webdisdik.jabarprov.go.id/next/api/v1/kalender"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

FETCH_DI_HALAMAN = """
async (url) => {
  const res = await fetch(url, { headers: { Accept: 'application/json' } });
  const text = await res.text();
  return { status: res.status, text };
}
"""


async def ambil(out: Path) -> int:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            locale="id-ID",
            timezone_id="Asia/Jakarta",
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 768},
        )
        page = await context.new_page()

        ditangkap: dict = {}

        async def simpan(resp):
            if "/next/api/v1/kalender" in resp.url and resp.status == 200 and "payload" not in ditangkap:
                try:
                    ditangkap["payload"] = await resp.json()
                    print(f"  tertangkap dari response: {resp.url}")
                except ValueError:
                    pass

        page.on("response", lambda r: asyncio.create_task(simpan(r)))

        print(f"Membuka {HALAMAN_URL}")
        await page.goto(HALAMAN_URL, wait_until="domcontentloaded", timeout=90_000)

        # Beri waktu challenge Cloudflare selesai dan halaman memuat data.
        for _ in range(10):
            if "payload" in ditangkap:
                break
            await page.wait_for_timeout(3_000)

        if "payload" not in ditangkap:
            print("  response API belum tertangkap, coba fetch dari dalam halaman")
            hasil = await page.evaluate(FETCH_DI_HALAMAN, API_URL)
            if hasil.get("status") == 200:
                ditangkap["payload"] = json.loads(hasil["text"])
            else:
                print(f"  HTTP {hasil.get('status')} dari dalam halaman")
                cuplikan = (hasil.get("text") or "")[:200].replace("\n", " ")
                print(f"  isi: {cuplikan}")

        await context.close()
        await browser.close()

    if "payload" not in ditangkap:
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(ditangkap["payload"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    jumlah = len(ditangkap["payload"].get("data") or [])
    print(f"  tersimpan: {out} ({jumlah} tahun ajaran)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default="data/.cache/api-kalender.json",
        help="lokasi simpan JSON mentah (default: data/.cache/api-kalender.json)",
    )
    args = parser.parse_args()
    out = Path(args.out)
    if not out.is_absolute():
        out = Path(__file__).resolve().parent.parent / out

    try:
        return asyncio.run(ambil(out))
    except Exception as exc:  # noqa: BLE001 - laporkan apa pun yang terjadi
        print(f"Gagal: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
