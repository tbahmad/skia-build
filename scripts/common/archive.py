#!/usr/bin/env python3
"""Helper pembuatan arsip rilis: tar.xz (Linux) & zip (Windows/Android),
plus pemetaan nama library canonical parana-libs.

Nama file arsip final (sesuai spesifikasi proyek):
  parana-libs-<platform>-<arch>-<buildtype-lower>.tar.gz|zip
    linux   -> .tar.xz   (mis. parana-libs-linux-x86_64-release.tar.xz)
    windows -> .zip      (mis. parana-libs-windows-x86_64-debug.zip)
    android -> .zip per ABI (mis. parana-libs-android-arm64-v8a-release.zip)
"""

import lzma, pathlib, sys, tarfile, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from util import load_config  # noqa: E402

# Nama library di dalam bundle -> nama canonical parana-libs (tanpa prefix lib).
# Skia MODUL disimpan dengan nama aslinya (libskottie.a dst.) karena konsumen
# men-link banyak modul; hanya 4 komponen utama yang dinormalkan.
CANON_LIBS = {
    "libskia.a": "libskia.a", "skia.lib": "skia.lib",
    "libSDL3.a": "libSDL3.a", "SDL3.lib": "SDL3.lib", "SDL3.dll": "SDL3.dll",
    "libSDL3.so": "libSDL3.so",
    "libquickjs.a": "libqjs.a", "quickjs.lib": "qjs.lib",
    "libyogacore.a": "libyoga.a", "yogacore.lib": "yoga.lib",
}


def canon_lib_name(name):
    """Petakan nama file lib dependency ke nama canonical (untuk manifest)."""
    return CANON_LIBS.get(name, name)


ARCH_DISPLAY = {"x64": "x86_64"}   # spesifikasi penamaan memakai x86_64


def display_arch(a):
    return ARCH_DISPLAY.get(a, a)


def archive_name(platform, arch, build_type, fmt=None):
    if fmt is None:
        fmt = load_config("platforms")[platform]["archive_format"]
    ext = {"tar.xz": ".tar.xz", "zip": ".zip"}[fmt]
    return f"parana-libs-{platform}-{display_arch(arch)}-{build_type.lower()}{ext}"


class _TarXZWriter:
    """tar + kompresi xz manual -> selalu menghasilkan ekstensi .tar.xz."""

    def __init__(self, path):
        self._raw = open(path, "wb")
        self._xz = lzma.LZMACompressor(preset=6)
        self._tf = tarfile.open(fileobj=self, mode="w|")   # streamable

    def write(self, data):
        self._raw.write(self._xz.compress(data))

    def add(self, src, arcname):
        self._tf.add(str(src), arcname=arcname)

    def add_bytes(self, arcname, data, mode=0o644):
        ti = tarfile.TarInfo(arcname)
        ti.size = len(data)
        ti.mode = mode
        self._tf.addfile(ti, fileobj=__import__("io").BytesIO(data))

    def close(self):
        self._tf.close()
        self._raw.write(self._xz.flush())
        self._raw.close()


class _ZipWriter:
    def __init__(self, path):
        self._zf = zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED)

    def add(self, src, arcname):
        self._zf.write(str(src), arcname=arcname)

    def add_bytes(self, arcname, data, mode=None):
        self._zf.writestr(arcname, data)

    def close(self):
        self._zf.close()


def open_archive(path, fmt):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "tar.xz":
        return _TarXZWriter(p)
    if fmt == "zip":
        return _ZipWriter(p)
    raise ValueError(f"format tidak dikenal: {fmt}")
