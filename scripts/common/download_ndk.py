#!/usr/bin/env python3
"""Unduh & ekstrak Android NDK r27c ke ./android-ndk (bisa dipakai build_android.py).

Skia mendukung NDK r23+; r27 adalah versi LTS yang direkomendasikan.
Jika ANDROID_NDK_ROOT sudah diset dan valid, langkah ini dilewati.
"""

import os, shutil, subprocess, sys, tarfile, urllib.request

NDK_VERSION = "27.2.12479018"
NDK_NAME = f"android-ndk-r27c"
NDK_URL = ("https://dl.google.com/android/repository/"
           f"android-ndk-r27c-linux.zip")


def main():
    os.chdir(os.path.join(os.path.dirname(__file__), os.pardir))
    root = os.getcwd()

    existing = os.environ.get("ANDROID_NDK_ROOT", "")
    if existing and os.path.isdir(existing):
        print("> NDK sudah tersedia di:", existing)
        return 0

    dest = os.path.join(root, "android-ndk")
    if os.path.isdir(dest) and os.path.isdir(os.path.join(dest, "toolchains")):
        print("> NDK sudah ada di:", dest)
        return 0

    print(f"> Mengunduh {NDK_NAME} (~600 MB) ...")
    zipfile_path = os.path.join(root, "ndk.zip")
    with urllib.request.urlopen(NDK_URL) as resp, open(zipfile_path, "wb") as f:
        total = int(resp.headers.get("Content-Length", 0))
        done = 0
        while True:
            chunk = resp.read(1 << 22)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                pct = 100 * done // total
                if pct % 10 == 0:
                    print(f"  ... {pct}%")

    print("> Mengekstrak ...")
    import zipfile as _zip
    with _zip.ZipFile(zipfile_path) as zf:
        # folder teratas bernama android-ndk-r27c -> rename menjadi android-ndk
        top = os.path.commonprefix([i for i in zf.namelist() if i])
        zf.extractall(root)
    extracted = os.path.join(root, NDK_NAME)
    if os.path.isdir(extracted):
        if os.path.exists(dest):
            shutil.rmtree(dest)
        os.rename(extracted, dest)
    os.remove(zipfile_path)

    if not os.path.isdir(os.path.join(dest, "toolchains")):
        sys.exit("ERROR: ekstraksi NDK tidak menghasilkan struktur yang benar")
    print("> NDK siap di:", dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
