#!/usr/bin/env python3
"""Utilitas umum lintas-modul: path proyek, config, logging, eksekusi proses.

Semua modul di scripts/ (common/, dependencies/, build.py, package.py)
mengimpor dari sini supaya tidak ada duplikasi helper.
"""

import json, os, pathlib, subprocess, sys

# root repo = dua level di atas file ini (scripts/common/util.py -> repo)
ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = ROOT / "config"
PATCHES_DIR = ROOT / "patches"
CACHE_DIR = ROOT / "third_party" / "_cache"
WORK_DIR = ROOT / "work"          # sumber dependency yang di-download
DIST_DIR = ROOT / "dist"          # staging hasil build per komponen
OUT_DIR = ROOT / "out"            # arsip final parana-libs-*


def load_config(name):
    """Baca config/<name>.json (versions | platforms | build-options)."""
    return json.loads((CONFIG_DIR / f"{name}.json").read_text(encoding="utf-8"))


def log(*args):
    print(">", *args, flush=True)


def warn(*args):
    print("WARNING:", *args, flush=True)


def die(*args):
    print("ERROR:", *args, file=sys.stderr, flush=True)
    sys.exit(1)


def sh(cmd, cwd=None, env=None, check=True, capture=False):
    """Jalankan perintah (list arg); echo dulu agar terbaca di log Actions."""
    cmd = [str(c) for c in cmd]
    log("$", " ".join(cmd))
    kw = dict(cwd=str(cwd) if cwd else None, env=env)
    if capture:
        kw.update(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    r = subprocess.run(cmd, **kw)
    if check and r.returncode != 0:
        die(f"perintah gagal (exit {r.returncode}): {' '.join(cmd)}")
    return r


def host_system():
    """Nama platform canonical: linux | windows | macos."""
    return {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}[os.uname().sysname \
           if hasattr(os, "uname") else __import__("platform").system()]


def canon_arch(system, arch):
    """Normalisasi nama arch via config/platforms.json arch_aliases."""
    plat = load_config("platforms").get(system, {})
    aliases = plat.get("arch_aliases", {})
    for canon, names in aliases.items():
        if arch == canon or arch in names:
            return canon
    return arch


def safe_name(s):
    """Sanitasi string untuk dipakai sebagai nama file/artifact GitHub."""
    import re
    return re.sub(r"[^A-Za-z0-9._+-]", "_", str(s))


def git_short_head(repo_dir, n=10):
    try:
        return subprocess.check_output(["git", "-C", str(repo_dir), "rev-parse",
                                        "--short=12", "HEAD"]).decode().strip()[:n]
    except Exception:
        return ""
