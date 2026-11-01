#!/usr/bin/env python3
"""Ambil dependency non-Skia untuk bundle prebuilt: SDL3, Yoga, QuickJS.

Semua sumber resmi (tanpa kompilasi manual):
  * SDL3    : release resmi libsdl-org/SDL
              - Windows MSVC -> SDL3-devel-<v>-VC.zip   (SDL3.lib + SDL3.dll + include/)
              - Linux        -> source tarball, di-build via CMake (SDL3-static)
              - Android      -> SDL3-devel-<v>-android.zip (aar; JNI + headers saja)
  * Yoga    : source facebook/yoga (branch/tag dari versions.json),
              di-build via CMake menjadi libyogacore.a / yogacore.lib per target
  * QuickJS : quickjs-ng/quickjs — source tarball + binari qjs/qjsc resmi
              (dirilis tanpa lib statis; header + amalgam disertakan)

Konfigurasi versi: third_party/versions.json

Struktur hasil (di bawah root repo):
  dist/<system>/include/{SDL3,yoga,quickjs}/...
  dist/<system>/lib/[<abi>/]SDL3.* yoga.* quickjs.* (+ dll/runtime bila ada)
  dist/<system>/bin/qjs[.exe] qjsc[.exe]
  dist/<system>/licenses/LICENSE.{SDL3,yoga,quickjs}
"""

import argparse, io, json, os, pathlib, platform, re, shutil, subprocess, sys, tarfile, zipfile, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"


# ------------------------------------------------------------------ util ----
def download(url, dst=None, timeout=180):
    print("> GET", url)
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        blob = resp.read()
    if dst:
        pathlib.Path(dst).write_bytes(blob)
        return pathlib.Path(dst)
    return blob


def extract_zip(blob_or_path, dest):
    zf = zipfile.ZipFile(io.BytesIO(blob_or_path) if isinstance(blob_or_path, bytes)
                         else str(blob_or_path))
    zf.extractall(dest)


def extract_tar(blob_or_path, dest):
    tf = tarfile.open(fileobj=io.BytesIO(blob_or_path), mode="r:*") \
        if isinstance(blob_or_path, bytes) else tarfile.open(str(blob_or_path), "r:*")
    tf.extractall(dest)


def sh(cmd, cwd=None, env=None, check=True):
    print(">", " ".join(str(c) for c in cmd))
    r = subprocess.run([str(c) for c in cmd], cwd=str(cwd) if cwd else None, env=env)
    if check and r.returncode != 0:
        sys.exit(f"ERROR: perintah gagal (exit {r.returncode}): {' '.join(map(str, cmd))}")
    return r.returncode


def load_versions():
    return json.loads((ROOT / "third_party" / "versions.json").read_text())


def git_sha(repo_dir):
    try:
        return subprocess.check_output(["git", "-C", str(repo_dir), "rev-parse", "--short", "HEAD"]).decode().strip()
    except Exception:
        return ""


# ------------------------------------------------------------------ SDL3 ----
def fetch_sdl(vers, src_dir, system, machine):
    """Kembalikan dict info SDL (path library, runtime, include_root, version)."""
    v = vers["sdl"]["version"]
    tag = vers["sdl"].get("tag", f"release-{v}")
    base = f"https://github.com/libsdl-org/SDL/releases/download/{tag}"
    out = {}

    # Android: selalu pakai aar resmi (.so per ABI + JNI), bukan build static.
    if system == "android":
        p = download(f"{base}/SDL3-devel-{v}-android.zip", src_dir / "SDL3-android.zip")
        ex = src_dir / "sdl-aar"
        extract_zip(p, ex)
        aar = next(ex.glob("*.aar"))
        ex2 = ex / "aar"
        extract_zip(aar, ex2)
        out.update(lib_stem=None, runtime=None, include_root=ex2 / "include",
                   license=ex2 / "LICENSE.txt" if (ex2 / "LICENSE.txt").is_file()
                   else ex / "LICENSE.txt", version=v,
                   jni=list((ex2 / "jni").glob("**/*.so")) if (ex2 / "jni").is_dir() else [],
                   java=[str(x) for x in ex2.glob("*.jar")])
        return out

    if system == "windows":
        p = download(f"{base}/SDL3-devel-{v}-VC.zip", src_dir / "SDL3-VC.zip")
        ex = src_dir / "sdl-extract"
        extract_zip(p, ex)
        root = next(ex.iterdir())          # SDL3-<v>/
        libx = root / "lib" / "x64"
        out.update(lib_stem=libx / "SDL3.lib", runtime=root / "lib" / "x64" / "SDL3.dll",
                   include_root=root / "include", license=root / "LICENSE.txt", version=v)
    elif system == "linux":
        p = download(f"{base}/SDL3-{v}.tar.gz", src_dir / f"SDL3-{v}.tar.gz")
        src = src_dir / "SDL3-src"
        extract_tar(p, src)
        root = next(src.iterdir())         # SDL3-<v>/
        bld = root / "build"
        cmake_args = ["-DCMAKE_BUILD_TYPE=Release", "-DSDL_STATIC=ON", "-DSDL_SHARED=OFF",
                      "-DSDL_TESTS=OFF", "-DSDL_EXAMPLES=OFF", "-DSDL_JPEG=OFF",
                      "-DSDL_VULKAN=ON", "-DSDL_OPENGL=ON"]
        sh(["cmake", "-S", root, "-B", bld] + cmake_args)
        jobs = os.cpu_count() or 2
        sh(["cmake", "--build", bld, "-j", str(jobs), "--target", "SDL3-static"])
        lib = next(iter(bld.glob("**/libSDL3.a")), None) or next(iter(bld.glob("**/SDL3*.a")), None)
        if not lib:
            sys.exit("ERROR: libSDL3.a tidak ditemukan setelah build SDL3")
        out.update(lib_stem=lib, runtime=None, include_root=root / "include",
                   license=root / "LICENSE.txt", version=v)
    else:
        sys.exit(f"ERROR: sistem tidak didukung untuk SDL3: {system}")
    return out


# ------------------------------------------------------------------ Yoga ----
def fetch_yoga(vers, src_dir, system, machine, cmake_env=None):
    ref = vers["yoga"].get("ref", "main")
    url = f"https://github.com/facebook/yoga/archive/refs/{('tags/' if ref.startswith('v') else 'heads/')}{ref}.tar.gz"
    p = download(url, src_dir / "yoga.tar.gz")
    ext = src_dir / "yoga-src"
    extract_tar(p, ext)
    root = next(ext.iterdir())             # yoga-main/
    bld = root / "build"
    cmake_args = ["-DCMAKE_BUILD_TYPE=Release", "-DBUILD_TESTING=OFF",
                  "-DYOGA_BUILD_TESTS=OFF", "-DCMAKE_POSITION_INDEPENDENT_CODE=ON"]
    sh(["cmake", "-S", root, "-B", bld] + cmake_args, env=cmake_env)
    sh(["cmake", "--build", bld, "-j", str(os.cpu_count() or 2), "--target", "yogacore"], env=cmake_env)
    lib = next(iter(bld.glob("**/libyogacore.a")), None) or next(iter(bld.glob("**/yogacore.lib")), None)
    if not lib:
        sys.exit("ERROR: librari yogacore tidak ditemukan setelah build")
    return dict(lib_stem=lib, include_root=root / ".", license=root / "LICENSE",
                version=f"{ref}-{git_sha(root) or 'tarball'}")


# --------------------------------------------------------------- QuickJS ----
def fetch_quickjs(vers, src_dir, system, machine):
    v = vers["quickjs"]["version"]
    repo = vers["quickjs"].get("repo", "quickjs-ng/quickjs")
    p = download(f"https://github.com/{repo}/releases/download/v{v}/quickjs-amalgam.zip",
                 src_dir / "quickjs-amalgam.zip")
    ext = src_dir / "quickjs"
    ext.mkdir(parents=True, exist_ok=True)
    extract_zip(p, ext)                    # berisi quickjs.c/h, quickjs-libc.*, ...
    files = sorted(x.name for x in ext.iterdir())
    # binari CLI resmi (qjs/qjsc) untuk host saat ini
    bins = {}
    plat_map = {("linux", "x64"): "linux-x86_64", ("windows", "x64"): "windows-x86_64",
                ("macos", "x64"): "darwin-x86_64", ("macos", "arm64"): "darwin-arm64"}
    key = plat_map.get((system, machine))
    bin_dir = DIST / system / "bin"
    if key:
        bin_dir.mkdir(parents=True, exist_ok=True)
        exe = ".exe" if system == "windows" else ""
        for name in ("qjs", "qjsc"):
            try:
                blobs = download(f"https://github.com/{repo}/releases/download/v{v}/{name}-{key}{exe}")
                dst = bin_dir / (name + exe)
                dst.write_bytes(blobs)
                os.chmod(dst, 0o755)
                bins[name] = dst
            except Exception as e:
                print(f"WARNING: unduh {name}-{key} gagal: {e}")
    else:
        print(f"> QuickJS: tidak ada binari resmi untuk ({system},{machine}); hanya source+header.")
    return dict(include_root=ext, license=None, version=v, files=files, bins=bins)


# ------------------------------------------------------------------ main ----
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--system", default={"Darwin": "macos", "Linux": "linux",
                                             "Windows": "windows"}[platform.system()])
    parser.add_argument("--machine", default={"AMD64": "x64", "x86_64": "x64",
                                              "arm64": "arm64"}.get(platform.machine(), "x64"))
    parser.add_argument("--out-subdir", default=None,
                        help="Sub-direktori dist (default: nama sistem)")
    args = parser.parse_args()

    system = os.environ.get("SKIA_TARGET_OS") or args.system   # override utk android
    machine = args.machine
    out_name = args.out_subdir or system
    out_root = DIST / out_name
    src_dir = ROOT / "third_party" / "_cache"
    src_dir.mkdir(parents=True, exist_ok=True)

    vers = load_versions()
    inc = out_root / "include"
    lib = out_root / "lib"
    lic = out_root / "licenses"
    for d in (inc, lib, lic):
        d.mkdir(parents=True, exist_ok=True)

    summary = {}

    # --- SDL3 ---------------------------------------------------------------
    sdl = fetch_sdl(vers, src_dir, system, machine)
    if system == "android":
        # simpan .so per ABI apa adanya + headers
        for so in sdl.get("jni", []):
            abi = pathlib.Path(so).parent.name       # arm64-v8a, armeabi-v7a, x86, x86_64
            (lib / abi).mkdir(parents=True, exist_ok=True)
            shutil.copy2(so, lib / abi / pathlib.Path(so).name)
        shutil.copytree(sdl["include_root"], inc / "SDL3", dirs_exist_ok=True)
        summary["sdl"] = {"version": sdl["version"], "kind": "aar (shared .so + JNI)",
                          "abis": sorted({p.parent.name for p in map(pathlib.Path, sdl.get("jni", []))})}
    else:
        shutil.copytree(pathlib.Path(sdl["include_root"]) / "SDL3", inc / "SDL3", dirs_exist_ok=True)
        shutil.copy2(sdl["lib_stem"], lib / pathlib.Path(sdl["lib_stem"]).name)
        if sdl.get("runtime"):
            (out_root / "bin").mkdir(exist_ok=True)
            shutil.copy2(sdl["runtime"], out_root / "bin" / pathlib.Path(sdl["runtime"]).name)
        shutil.copy2(sdl["license"], lic / "LICENSE.SDL3.txt")
        summary["sdl"] = {"version": sdl["version"], "lib": pathlib.Path(sdl["lib_stem"]).name,
                          "runtime": bool(sdl.get("runtime"))}

    # --- Yoga ---------------------------------------------------------------
    yg = fetch_yoga(vers, src_dir, system, machine)
    shutil.copytree(yg["include_root"] / "yoga", inc / "yoga", dirs_exist_ok=True)
    shutil.copy2(yg["lib_stem"], lib / pathlib.Path(yg["lib_stem"]).name)
    shutil.copy2(yg["license"], lic / "LICENSE.yoga.txt")
    summary["yoga"] = {"version": yg["version"], "lib": pathlib.Path(yg["lib_stem"]).name}

    # --- QuickJS ------------------------------------------------------------
    qj = fetch_quickjs(vers, src_dir, system, machine)
    shutil.copytree(qj["include_root"], inc / "quickjs", dirs_exist_ok=True)
    (lic / "LICENSE.quickjs.txt").write_text(
        "QuickJS (quickjs-ng) - MIT license. See https://github.com/quickjs-ng/quickjs\n")
    summary["quickjs"] = {"version": qj["version"], "source_files": qj["files"],
                          "bins": {k: str(v.relative_to(out_root)) for k, v in qj["bins"].items()}}

    (out_root / "deps-info.json").write_text(json.dumps(summary, indent=2))
    print("\n> Ringkasan dependency ->", out_root)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
