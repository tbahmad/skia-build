#!/usr/bin/env python3
"""Checkout depot_tools + Skia (adaptasi dari JetBrains/skia-build, di-update).

Perbedaan dari versi JetBrains (m93):
  - Tidak perlu python2 untuk git-sync-deps (Skia modern sudah python3).
  - Versi menerima "main", "chrome/mNNN", tag, atau commit hash;
    format lama "mNNN-<sha>" tetap didukung.
  - Patch diterapkan dengan `git apply --3way` dan tidak gagal keras jika
    patch sudah tidak relevan di versi baru (hanya warning).
"""

import argparse, os, pathlib, re, subprocess, sys

SKIA_URL = "https://skia.googlesource.com/skia"


def main():
    os.chdir(os.path.join(os.path.dirname(__file__), os.pardir))

    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=os.environ.get("SKIA_VERSION", "main"))
    args = parser.parse_args()
    version = args.version

    # --- depot_tools ---------------------------------------------------------
    if not os.path.exists("depot_tools"):
        subprocess.check_call(
            ["git", "clone", "--depth", "1",
             "https://chromium.googlesource.com/chromium/tools/depot_tools.git",
             "depot_tools"]
        )

    # --- Skia ----------------------------------------------------------------
    # Format mNNN-sha (gaya JetBrains) -> branch chrome/mNNN, checkout sha
    m = re.match(r"^(m\d+)-([0-9a-f]{7,40})$", version)
    if m:
        branch, commit = "chrome/" + m.group(1), m.group(2)
    elif version.startswith("chrome/") or version == "main":
        branch, commit = version, None
    elif re.match(r"^[0-9a-f]{40}$", version):
        branch, commit = "main", version
    else:
        # anggap sebagai ref/tag lain
        branch, commit = version, None

    if os.path.exists("skia"):
        os.chdir("skia")
        subprocess.check_call(["git", "fetch", "origin", branch])
        subprocess.check_call(["git", "checkout", "-B", branch.replace("/", "_"), "FETCH_HEAD"])
    else:
        print("> Cloning", branch)
        # clone hanya branch yang dibutuhkan agar hemat waktu/disk
        subprocess.check_call(["git", "clone", SKIA_URL, "--quiet", "--branch", branch, "skia"])
        os.chdir("skia")

    if commit:
        print("> Checking out", commit)
        if len(commit) == 40 and os.path.exists(".git"):
            r = subprocess.run(["git", "cat-file", "-e", commit], capture_output=True)
            if r.returncode != 0:
                subprocess.check_call(["git", "fetch", "origin", commit])
        subprocess.check_call(["git", "-c", "advice.detachedHead=false", "checkout", commit])

    head = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    print("> HEAD:", head[:10])

    # --- patches -------------------------------------------------------------
    # Catatan penting: gunakan `git apply` BUKAN `git apply --3way`.
    # Dengan --3way, patch yang gagal akan meninggalkan file dalam status
    # "needs merge" (conflict) dan membuat git checkout berikutnya gagal.
    subprocess.check_call(["git", "reset", "--hard"])
    subprocess.check_call(["git", "clean", "-fd"])
    patches_dir = pathlib.Path(__file__).resolve().parent.parent / "patches"
    for x in sorted(patches_dir.glob("*.patch")):
        print("> Applying", x.name)
        r = subprocess.run(["git", "apply", str(x)])
        if r.returncode != 0:
            print(f"WARNING: {x.name} tidak cocok dengan versi ini -- dilewati.")
            subprocess.check_call(["git", "checkout", "--", "."])

    # --- third_party deps ----------------------------------------------------
    env = os.environ.copy()
    dt = os.path.abspath(os.path.join(os.pardir, "depot_tools"))
    env["PATH"] = dt + os.pathsep + env.get("PATH", "")
    subprocess.check_call([sys.executable, "tools/git-sync-deps"], env=env)

    return 0


if __name__ == "__main__":
    sys.exit(main())
