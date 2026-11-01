#!/usr/bin/env python3
"""Dependency module: Skia (checkout + build host, gn/ninja).

Gabungan pipeline warisan yang sudah teruji di CI:
  checkout() : depot_tools bootstrap (non-fatal di Windows), clone branch
               chrome/mNNN/main, patch non-fatal, git-sync-deps, jaminan gn/ninja.
  build()    : gn gen + ninja memakai GN args dari config/build-options.json.

API baru `prepare()` mem staging hasil ke layout parana-libs agar seragam
dengan dependency lain (include/skia/, lib/<arch>/..., bin/icudtl.dat,
licenses/LICENSE.Skia.txt).
"""

import glob, os, pathlib, re, shutil, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common import patch as patch_mod, util  # noqa: E402
from common.util import ROOT, CONFIG_DIR, DIST_DIR, log, warn, die, sh, load_config  # noqa: E402

SKIA_URL = "https://skia.googlesource.com/skia"
SKIA_DIR = ROOT / "skia"
DT_DIR = ROOT / "depot_tools"

# modul esensial yang ikut di-build & di-arsip (konsisten dgn ninja_targets)
MODULES = ["skia", "skottie", "skparagraph", "skshaper", "svg"]
DEP_PREFIXES = ("expat", "freetype", "harfbuzz", "icu", "jpeg", "png",
                "webp", "z", "sfntly")


def _env_dt():
    env = os.environ.copy()
    env["PATH"] = str(DT_DIR) + os.pathsep + env.get("PATH", "")
    env.setdefault("DEPOT_TOOLS_UPDATE", "0")
    env.setdefault("HOME", os.getcwd())
    return env


def _run_bootstrap(script_name):
    """Jalankan script bootstrap depot_tools, kompatibel Linux & Windows.

    Di Windows 'ensure_bootstrap' adalah shell script bash tanpa ekstensi ->
    WinError 193 bila dipanggil langsung; pakai .bat atau skip.
    """
    env = _env_dt()
    bat = DT_DIR / (script_name + ".bat")
    shx = DT_DIR / script_name
    if os.name == "nt":
        if bat.is_file():
            return subprocess.run([str(bat)], env=env, shell=True)
        log(f"{script_name}.bat tidak ditemukan; skip (Windows).")
        class _R: returncode = 0
        return _R()
    return subprocess.run([str(shx)], env=env)


def fetch_gn_cipd():
    """Unduh binari gn.exe resmi dari CIPD (fallback Windows paling andal)."""
    import io, urllib.request, zipfile
    url = "https://chrome-infra-packages.appspot.com/dl/gn/gn/windows-amd64/+/latest"
    dst_dir = DT_DIR / "cipd-bin"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / "gn.exe"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            blob = resp.read()
        zf = zipfile.ZipFile(io.BytesIO(blob))
        with zf.open("gn.exe") as src, open(dst, "wb") as out:
            shutil.copyfileobj(src, out)
    except Exception as e:
        warn(f"unduh gn dari CIPD gagal: {e}")
        return None
    log("gn binari resmi CIPD:", dst)
    return dst


def build_gn_from_source():
    """Compile gn dari skia/tools/gn pakai MSVC (fallback terakhir)."""
    gn_src = SKIA_DIR / "tools" / "gn"
    if not gn_src.is_dir():
        return None
    log("Meng-compile gn dari source (tools/gn) ...")
    rc = subprocess.call([sys.executable, "bootstrap.py"], cwd=gn_src, env=_env_dt())
    cand = gn_src / "Release_x64" / "gn.exe"
    if rc != 0 or not cand.is_file():
        return None
    dst = DT_DIR / "gn.exe"
    shutil.copy(cand, dst)
    return dst


def checkout(version=None):
    version = version or os.environ.get("SKIA_VERSION") \
        or load_config("versions")["skia"]["ref"]

    if not DT_DIR.exists():
        sh(["git", "clone", "--depth", "1",
            "https://chromium.googlesource.com/chromium/tools/depot_tools.git",
            str(DT_DIR)])

    reldir = DT_DIR / "python3_bin_reldir.txt"
    if not reldir.exists():
        log("Bootstrapping depot_tools ...")
        r = _run_bootstrap("ensure_bootstrap")
        if r.returncode != 0 and not reldir.exists():
            _run_bootstrap("update_depot_tools")
        if not reldir.exists() and os.name == "nt":
            if not shutil.which("ninja"):
                die("depot_tools gagal di-bootstrap dan 'ninja' tidak ada di PATH. "
                    "Pastikan step 'Install ninja' di workflow berhasil.")
            log("Bootstrap depot_tools dilewati (Windows); ninja dari PATH, "
                "gn akan disiapkan setelah checkout.")
        elif not reldir.exists():
            die("depot_tools gagal di-bootstrap (python3_bin_reldir.txt tidak ada)")
    else:
        log("depot_tools sudah ter-bootstrap.")

    def _is_exec(p):
        return os.path.isfile(p) and os.access(p, os.X_OK)

    for tool in ("gn", "ninja"):
        target = DT_DIR / (tool + (".exe" if os.name == "nt" else ""))
        if _is_exec(target) or shutil.which(tool):
            continue
        if os.name == "nt":
            log(f"{tool}: prefetch dilewati (Windows); ditangani langkah lain.")
            continue
        r = subprocess.run([str(DT_DIR / "download_from_google_storage"),
                            "--no_auth", "--recursive", "--num_threads", "8",
                            "-o", str(target), f"skia/third_party/{tool}"], env=_env_dt())
        if r.returncode != 0:
            warn(f"prefetch {tool} gagal; akan dicoba saat git-sync-deps/gn gen.")

    m = re.match(r"^(m\d+)-([0-9a-f]{7,40})$", version)
    if m:
        branch, commit = "chrome/" + m.group(1), m.group(2)
    elif version.startswith("chrome/") or version == "main":
        branch, commit = version, None
    elif re.match(r"^[0-9a-f]{40}$", version):
        branch, commit = "main", version
    else:
        branch, commit = version, None

    if SKIA_DIR.exists():
        sh(["git", "-C", SKIA_DIR, "fetch", "origin", branch], check=False)
        sh(["git", "-C", SKIA_DIR, "checkout", "-B", branch.replace("/", "_"), "FETCH_HEAD"])
    else:
        log("Cloning", branch)
        sh(["git", "clone", SKIA_URL, "--quiet", "--branch", branch, str(SKIA_DIR)])

    if commit:
        head_exists = subprocess.run(["git", "-C", SKIA_DIR, "cat-file", "-e", commit],
                                     capture_output=True).returncode == 0
        if len(commit) == 40 and not head_exists:
            sh(["git", "-C", SKIA_DIR, "fetch", "origin", commit])
        sh(["git", "-C", SKIA_DIR, "-c", "advice.detachedHead=false", "checkout", commit])

    head = subprocess.check_output(["git", "-C", SKIA_DIR, "rev-parse", "HEAD"]).decode().strip()
    log("HEAD:", head[:10])

    if os.name == "nt" and not shutil.which("gn") and not (DT_DIR / "gn.exe").is_file():
        gn_bin = fetch_gn_cipd() or build_gn_from_source()
        if gn_bin is None:
            die("gn tidak tersedia di Windows (PATH/depot_tools/CIPD/source semua gagal).")

    sh(["git", "-C", SKIA_DIR, "reset", "--hard"])
    sh(["git", "-C", SKIA_DIR, "clean", "-fd"])
    stats = patch_mod.apply_all(SKIA_DIR)
    log(f"patch: {stats['applied']} diterapkan, {stats['skipped']} dilewati")

    r = subprocess.run([sys.executable, "tools/git-sync-deps"], cwd=SKIA_DIR, env=_env_dt())
    if r.returncode != 0:
        warn("git-sync-deps gagal, memakai fallback clone manual dari DEPS ...")
        _sync_deps_fallback(head)
    return {"version": version, "head": head}


def _sync_deps_fallback(head):
    import base64, urllib.request
    deps_txt = urllib.request.urlopen(
        f"https://skia.googlesource.com/skia/+/{head}/DEPS?format=TEXT").read().decode()
    try:
        deps_txt = base64.b64decode(deps_txt).decode()
    except Exception:
        pass
    for dm in re.finditer(r'"(third_party/externals/[^"]+)"\s*:\s*"([^"@]+)@([0-9a-f]{7,40})"',
                          deps_txt):
        path_, base_url, rev = dm.groups()
        p = SKIA_DIR / path_
        if p.exists():
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        if subprocess.run(["git", "clone", "--quiet", base_url, str(p)]).returncode != 0:
            continue
        subprocess.run(["git", "-C", str(p), "checkout", "--quiet", "-f", rev],
                       capture_output=True)
    missing = [x for x in ("freetype", "harfbuzz", "icu", "expat", "zlib")
               if not (SKIA_DIR / "third_party" / "externals" / x).exists()]
    if missing:
        die("dependency tidak lengkap:", ", ".join(missing))


def find_tool(name, system):
    """Cari binari gn/ninja asli; hindari wrapper depot_tools yang butuh bootstrap."""
    exe = name + (".exe" if system == "windows" else "")

    def usable(p):
        if not p or os.path.isdir(p):
            return False
        if system == "windows":
            return p.lower().endswith(".exe") and os.path.isfile(p)
        return os.access(p, os.X_OK)
    w = shutil.which(name)
    if usable(w):
        return w
    for cand in sorted(glob.glob(str(SKIA_DIR / "third_party" / name / "*" / exe))):
        if usable(cand):
            return cand
    for cand in sorted(glob.glob(str(DT_DIR / ".cipd" / "**" / exe), recursive=True)):
        if usable(cand):
            return cand
    for cand in (DT_DIR / exe, DT_DIR / "cipd-bin" / exe):
        if usable(str(cand)):
            return str(cand)
    return str(DT_DIR / exe)


def gn_args_for(platform, cpu, build_type, extra_overrides=None):
    """GN args dari config/build-options.json + override dinamis per target."""
    opts = load_config("build-options")
    args = list(opts["common"])
    args += opts["platform"].get(platform, [])
    args += opts["build_types"].get(build_type, ["is_debug=false", "is_component_build=false"])
    args.append(f'target_cpu="{cpu}"')
    if platform == "android":
        ndk = os.environ.get("ANDROID_NDK_ROOT") or str(ROOT / "android-ndk")
        args.append(f'ndk="{ndk}"')
    seen = {}
    for a in (args + list(extra_overrides or [])):
        seen[a.split("=", 1)[0]] = a
    return list(seen.values())


def build(platform="linux", machine="x64", build_type=None, abis=None, ndk=None):
    """Build Skia (host atau Android multi-ABI). Return dict out dirs per arch/abi."""
    build_type = build_type or os.environ.get("BUILD_TYPE", "Release")
    targets = load_config("build-options")["ninja_targets"]
    env = _env_dt()
    gn = find_tool("gn", "windows" if platform == "windows" else "linux")
    ninja = find_tool("ninja", "windows" if platform == "windows" else "linux")
    log("gn:", gn, "| ninja:", ninja)

    outs = {}
    jobs = str(os.cpu_count() or 2)
    todo = [(abi, load_config("platforms")["android"]["gn_cpu"][abi])
            for abi in (abis or [])] if platform == "android" else [(machine, machine)]
    failed = []
    for label, cpu in todo:
        if platform == "android" and cpu is None:
            warn(f"ABI tidak dikenal: {label} (skip)")
            failed.append(label)
            continue
        out = SKIA_DIR / "out" / f"{build_type}-{label}"
        args = gn_args_for(platform, cpu, build_type)
        log(f"[{label}] gn gen", out)
        rc = subprocess.call([gn, "gen", str(out), "--args=" + " ".join(args)],
                             env=env, cwd=str(SKIA_DIR))
        if rc != 0:
            ag = out / "args.gn"
            if ag.exists():
                print(ag.read_text())
            warn(f"gn gen gagal untuk {label} (exit {rc})")
            failed.append(label)
            continue
        rc = subprocess.call([ninja, "-C", str(out)] + targets, env=env, cwd=str(SKIA_DIR))
        if rc != 0:
            warn(f"ninja gagal untuk {label} (exit {rc})")
            failed.append(label)
            continue
        outs[label] = out
        log(f"[{label}] build selesai")
    if failed:
        die("build Skia gagal untuk:", ", ".join(failed))
    return outs


def find_libs(out_dir, suffix=".a"):
    libs = []
    for p in sorted(pathlib.Path(out_dir).glob("*" + suffix)):
        base = p.name.lstrip("lib").replace(suffix, "")
        if base in MODULES:
            libs.append(p)
            continue
        if any(base.startswith(d) or base == d for d in DEP_PREFIXES):
            libs.append(p)
    return libs


HEADER_PATTERNS = [
    "include/**/*.h", "include/private/*.h",
    "modules/particles/include/*.h", "modules/skottie/include/*.h",
    "modules/skottie/src/**/*.h", "modules/skparagraph/include/*.h",
    "modules/skplaintexteditor/include/*.h", "modules/skresources/include/*.h",
    "modules/sksg/include/*.h", "modules/skshaper/include/*.h",
    "modules/skshaper/src/*.h", "modules/svg/include/*.h",
    "src/**/*.h",
    "third_party/externals/freetype/include/**/*.h",
    "third_party/externals/harfbuzz/src/**/*.h",
    "third_party/externals/icu/source/common/**/*.h",
    "third_party/externals/icu/source/i18n/**/*.h",
    "third_party/externals/libpng/*.h",
    "third_party/externals/libwebp/src/**/*.h",
    "third_party/externals/zlib/*.h",
    "third_party/externals/expat/**/*.h",
]


def collect_headers():
    seen, result = set(), []
    for pat in HEADER_PATTERNS:
        for p in SKIA_DIR.glob(pat):
            if not p.is_file():
                continue
            rel = str(p.relative_to(SKIA_DIR)).replace("\\", "/")
            if rel in seen:
                continue
            seen.add(rel)
            result.append((rel, p))
    return result


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkout", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--version", default=None)
    ap.add_argument("--platform", default="linux")
    ap.add_argument("--machine", default="x64")
    ap.add_argument("--build-type", default=None)
    ap.add_argument("--abis", default="")
    a = ap.parse_args()
    if a.checkout:
        checkout(a.version)
    if a.build:
        build(a.platform, a.machine, a.build_type,
              [x.strip() for x in a.abis.split(",") if x.strip()] or None)
