#!/usr/bin/env python3
"""Helper ekstraksi arsip (zip/tar) dengan filter aman, dipakai dependency module."""

import io, os, pathlib, shutil, sys, tarfile, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from util import log  # noqa: E402


def extract_zip(src, dest):
    """Ekstrak zip dari bytes/Path ke dest. Aman terhadap path traversal."""
    dest = pathlib.Path(dest)
    zf = zipfile.ZipFile(io.BytesIO(src) if isinstance(src, (bytes, bytearray)) else str(src))
    for member in zf.infolist():
        target = (dest / member.filename).resolve()
        if not str(target).startswith(str(dest.resolve())):
            raise RuntimeError(f"illegal zip path: {member.filename}")
    zf.extractall(dest)
    return dest


def extract_tar(src, dest):
    """Ekstrak tar(.gz/.xz/*) dari bytes/Path ke dest (filter='data' bila didukung)."""
    dest = pathlib.Path(dest)
    tf = tarfile.open(fileobj=io.BytesIO(src), mode="r:*") \
        if isinstance(src, (bytes, bytearray)) else tarfile.open(str(src), "r:*")
    try:
        tf.extractall(dest, filter="data")   # py>=3.12: aman dari path traversal
    except TypeError:                         # py<3.12 tidak punya arg filter
        tf.extractall(dest)
    return dest


def extract_any(src, dest):
    """Pilih ekstraktor berdasarkan magic bytes/ekstensi."""
    head = src[:2] if isinstance(src, (bytes, bytearray)) \
        else pathlib.Path(src).open("rb").read(2)
    if head == b"PK":
        return extract_zip(src, dest)
    if head[:2] == b"\x1f\x8b" or str(src).endswith((".tar", ".tar.gz", ".tgz", ".tar.xz")):
        return extract_tar(src, dest)
    raise RuntimeError(f"format arsip tidak dikenal: {src}")


def copy_tree(src, dst):
    """copytree yang meng-merge (dirs_exist_ok untuk py3.7 compat eksplisit)."""
    src, dst = pathlib.Path(src), pathlib.Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for p in src.rglob("*"):
        if p.is_file():
            rel = p.relative_to(src)
            out = dst / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, out)
    return dst
