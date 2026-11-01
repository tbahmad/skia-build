#!/usr/bin/env python3
"""Shim kompatibilitas: modul Android digabung ke dependencies/skia.py.

Skia Android kini ditangani `skia.build(platform="android", abis=[...])`
(dipanggil otomatis oleh scripts/build.py --platform android).
File ini dipertahankan agar pemanggil lama tidak rusak.
"""
import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dependencies import skia as _skia  # noqa: E402


def checkout(version=None):
    return _skia.checkout(version)


def build_abis(abis, build_type="Release"):
    return _skia.build("android", "x64", build_type, abis)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkout", action="store_true")
    ap.add_argument("--abis", default="arm64-v8a")
    a = ap.parse_args()
    if a.checkout:
        checkout()
    build_abis([x.strip() for x in a.abis.split(",") if x.strip()])
