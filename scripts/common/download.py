#!/usr/bin/env python3
"""Helper download file (HTTP/HTTPS) dengan retry, dipakai semua dependency module."""

import pathlib, sys, time, urllib.error, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from util import log  # noqa: E402


def download(url, dst=None, timeout=180, retries=3):
    """Ambil URL -> bytes, atau tulis ke `dst` (Path). Retry + backoff.

    Bisa di-patch dari test: `download.__code__` tidak; gunakan modul ini
    sebagai titik injeksi (dependency memanggil modul.download).
    """
    last = None
    for attempt in range(1, retries + 1):
        try:
            log(f"GET ({attempt}/{retries})", url)
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                blob = resp.read()
            if dst:
                dst = pathlib.Path(dst)
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(blob)
                return dst
            return blob
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
            log(f"  gagal: {e}; retry dalam {5 * attempt}s ...")
            time.sleep(5 * attempt)
    raise RuntimeError(f"download gagal setelah {retries}x: {url}") from last
