#!/usr/bin/env python3
"""Aplikasi patch git secara non-fatal (perilaku warisan pipeline lama)."""

import pathlib, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from util import PATCHES_DIR, log, warn  # noqa: E402


def apply_all(repo_dir, patches_dir=None):
    """Terapkan semua *.patch di patches_dir ke repo_dir.

    Catatan penting (lesson learned pipeline lama): pakai `git apply` BUKAN
    `--3way`; dengan --3way patch yang gagal meninggalkan file 'needs merge'
    dan merusak git checkout berikutnya. Patch yang tidak cocok -> warning +
    restore, bukan fatal.
    """
    patches_dir = pathlib.Path(patches_dir) if patches_dir else PATCHES_DIR
    applied = skipped = 0
    for x in sorted(patches_dir.glob("*.patch")):
        log("Applying", x.name)
        r = subprocess.run(["git", "-C", str(repo_dir), "apply", str(x)])
        if r.returncode != 0:
            warn(f"{x.name} tidak cocok dengan versi ini -- dilewati.")
            subprocess.run(["git", "-C", str(repo_dir), "checkout", "--", "."])
            skipped += 1
        else:
            applied += 1
    return {"applied": applied, "skipped": skipped}
