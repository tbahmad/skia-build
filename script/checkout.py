#!/usr/bin/env python3
"""Checkout depot_tools + Skia (adaptasi dari JetBrains/skia-build, di-update).

Perbedaan dari versi JetBrains (m93):
  - Tidak perlu python2 untuk git-sync-deps (Skia modern sudah python3).
  - Versi menerima "main", "chrome/mNNN", tag, atau commit hash;
    format lama "mNNN-<sha>" tetap didukung.
  - Patch diterapkan dengan `git apply --3way` dan tidak gagal keras jika
    patch sudah tidak relevan di versi baru (hanya warning).
"""

import argparse, os, pathlib, re, shutil, subprocess, sys

SKIA_URL = "https://skia.googlesource.com/skia"


def main():
    os.chdir(os.path.join(os.path.dirname(__file__), os.pardir))

    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=os.environ.get("SKIA_VERSION", "main"))
    args = parser.parse_args()
    version = args.version

    # --- depot_tools ---------------------------------------------------------
    dt = os.path.abspath("depot_tools")
    if not os.path.exists(dt):
        subprocess.check_call(
            ["git", "clone", "--depth", "1",
             "https://chromium.googlesource.com/chromium/tools/depot_tools.git",
             "depot_tools"]
        )

    # Bootstrap depot_tools: membuat python3_bin_reldir.txt + mengunduh paket CIPD
    # (gn, ninja, dll). Tanpa langkah ini, wrapper depot_tools gagal dengan pesan
    #   "python3_bin_reldir.txt not found. need to initialize depot_tools..."
    env = os.environ.copy()
    env["DEPOT_TOOLS_UPDATE"] = "0"          # jangan self-update tiap pemanggilan
    env.setdefault("HOME", os.getcwd())      # hindari masalah HOME di runner
    cipd_root = os.path.join(os.getcwd(), ".cipd_root")
    os.makedirs(cipd_root, exist_ok=True)
    env["CIPD_CACHE_ROOT"] = cipd_root       # cache lokal agar unduhan tidak dobel
    reldir = os.path.join(dt, "python3_bin_reldir.txt")

    def _run_bootstrap(script_name):
        """Jalankan script bootstrap depot_tools, kompatibel Linux & Windows.

        Di Windows, 'ensure_bootstrap' / 'update_depot_tools' adalah shell script
        bash TANPA ekstensi -> subprocess langsung memicu WinError 193.
        Gunakan 'ensure_bootstrap.bat' bila ada; kalau tidak, skip bootstrap
        (gn/ninja akan disediakan dari PATH sistem oleh workflow).
        """
        bat = os.path.join(dt, script_name + ".bat")
        sh = os.path.join(dt, script_name)
        if os.name == "nt":
            if os.path.isfile(bat):
                return subprocess.run([bat], env=env, shell=True)
            print(f"> {script_name}.bat tidak ditemukan; skip (Windows).")
            class _R:  returncode = 0
            return _R()
        return subprocess.run([sh], env=env)

    if not os.path.exists(reldir):
        print("> Bootstrapping depot_tools ...")
        r = _run_bootstrap("ensure_bootstrap")
        if r.returncode != 0 and not os.path.exists(reldir):
            # fallback: panggil update_depot_tools (mengunduh gn/ninja juga)
            r2 = _run_bootstrap("update_depot_tools")
            if r2.returncode != 0 and os.name == "nt":
                pass  # di bawah ditangani lewat cek gn/ninja
        if not os.path.exists(reldir) and os.name == "nt":
            # Windows tanpa .bat: pastikan ninja tersedia dari PATH sistem.
            # gn akan di-compile dari source Skia setelah checkout (lihat bawah).
            if not __import__("shutil").which("ninja"):
                sys.exit("ERROR: depot_tools gagal di-bootstrap dan 'ninja' tidak ada "
                         "di PATH. Pastikan step 'Install ninja' di workflow berhasil.")
            print("> Bootstrap depot_tools dilewati (Windows); memakai ninja dari PATH, "
                  "gn akan di-compile dari source Skia.")
        elif not os.path.exists(reldir):
            sys.exit("ERROR: depot_tools gagal di-bootstrap (python3_bin_reldir.txt tidak ada)")
    else:
        print("> depot_tools sudah ter-bootstrap.")

    def fetch_gn_cipd():
        """Unduh gn.exe resmi binarinya dari CIPD chrome-infra-packages.

        Ini cara paling andal di Windows: tidak butuh depot_tools bootstrap
        dan tidak perlu meng-compile ulang tools/gn dengan MSVC.
        """
        import urllib.request, zipfile, io
        url = ("https://chrome-infra-packages.appspot.com/dl/"
               "gn/gn/windows-amd64/+/latest")
        dst_dir = os.path.join(dt, "cipd-bin")
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, "gn.exe")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                blob = resp.read()
            zf = zipfile.ZipFile(io.BytesIO(blob))
            with zf.open("gn.exe") as src, open(dst, "wb") as out:
                shutil.copyfileobj(src, out)
        except Exception as e:  # noqa
            print(f"WARNING: unduh gn dari CIPD gagal: {e}")
            return None
        print(f"> gn binari resmi CIPD: {dst}")
        return dst

    def build_gn_from_source():
        """Compile gn dari tools/gn bawaan Skia pakai MSVC (fallback terakhir)."""
        gn_src = os.path.abspath(os.path.join("skia", "tools", "gn"))
        if not os.path.isdir(gn_src):
            return None
        print("> Meng-compile gn dari source (tools/gn) ...")
        rc = subprocess.call([sys.executable, "bootstrap.py"], cwd=gn_src, env=env)
        cand = os.path.join(gn_src, "Release_x64", "gn.exe")
        if rc != 0 or not os.path.isfile(cand):
            return None
        dst = os.path.join(dt, "gn.exe")
        shutil.copy(cand, dst)
        print(f"> gn hasil compile: {dst}")
        return dst

    # Pastikan binari gn & ninja tersedia (build.py memakainya tanpa jaringan).
    def _is_exec(p):
        return os.path.isfile(p) and os.access(p, os.X_OK)

    sys_bin = {t: shutil.which(t) for t in ("gn", "ninja")}
    for tool in ("gn", "ninja"):
        target = os.path.join(dt, tool + (".exe" if os.name == "nt" else ""))
        if _is_exec(target) or sys_bin[tool]:
            print(f"> {tool} sudah tersedia.", end=" ")
            print("(depot_tools)" if _is_exec(target) else "(PATH sistem)")
            continue
        if os.name == "nt":
            # Di Windows tanpa bootstrap depot_tools, skip prefetch via
            # gcs (butuhnya CIPD). gn akan di-compile dari source setelah
            # checkout; ninja dipasok oleh step workflow.
            print(f"> {tool}: prefetch dilewati (Windows); ditangani langkah lain.")
            continue
        r = subprocess.run([os.path.join(dt, "download_from_google_storage"),
                            "--no_auth", "--recursive", "--num_threads", "8",
                            "-o", target,
                            "skia/third_party/" + tool], env=env)
        if r.returncode != 0:
            print(f"WARNING: prefetch {tool} gagal; akan dicoba saat git-sync-deps/gn gen.")

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

    # --- gn untuk Windows: unduh binari resmi CIPD, fallback compile source --
    # PENTING: blok ini dijalankan SETELAH skia ter-clone (fallback compile
    # membutuhkan skia/tools/gn yang baru ada setelah clone).
    if os.name == "nt" and not shutil.which("gn") \
            and not os.path.isfile(os.path.join(dt, "gn.exe")):
        os.chdir(os.path.abspath(os.pardir))  # keluar dari ./skia -> root repo
        gn_bin = fetch_gn_cipd()
        if gn_bin is None:
            gn_bin = build_gn_from_source()
        if gn_bin is None:
            sys.exit("ERROR: gn tidak tersedia di Windows (tidak ada di PATH, "
                     "depot_tools, gagal diunduh dari CIPD, dan gagal "
                     "di-compile dari tools/gn).")

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
    dtenv = os.environ.copy()
    dtenv["PATH"] = dt + os.pathsep + dtenv.get("PATH", "")
    dtenv["DEPOT_TOOLS_UPDATE"] = "0"
    r = subprocess.run([sys.executable, "tools/git-sync-deps"], env=dtenv)
    if r.returncode != 0:
        # fallback: parse DEPS sendiri dan clone langsung dari googlesource
        print("WARNING: git-sync-deps gagal, memakai fallback clone manual...")
        import urllib.request
        url = "https://skia.googlesource.com/skia/+" + head + "/DEPS?format=TEXT"
        deps_txt = urllib.request.urlopen(url).read().decode()
        import base64 as _b64  # noqa
        # jika API mengirim base64
        try:
            deps_txt = _b64.b64decode(deps_txt).decode()
        except Exception:
            pass
        for dm in re.finditer(r'"(third_party/externals/[^"]+)"\s*:\s*"([^"@]+)@([0-9a-f]{7,40})"',
                              deps_txt):
            path, base_url, rev = dm.groups()
            if os.path.isdir(path):
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            rr = subprocess.run(["git", "clone", "--quiet", base_url, path])
            if rr.returncode != 0:
                continue
            subprocess.run(["git", "-C", path, "checkout", "--quiet", "-f", rev],
                           capture_output=True)
        # pastikan direktori externals penting ada
        missing = [p for p in ("third_party/externals/freetype",
                               "third_party/externals/harfbuzz",
                               "third_party/externals/icu",
                               "third_party/externals/expat",
                               "third_party/externals/zlib")
                   if not os.path.exists(p)]
        if missing:
            sys.exit("ERROR: dependency tidak lengkap: " + ", ".join(missing))

    return 0


if __name__ == "__main__":
    sys.exit(main())
