#!/usr/bin/env python3
"""Dependency module: QuickJS (quickjs-ng).

Mengunduh amalgam resmi release, menyalin header+source ke staging, dan
membangun library statis canonical `libqjs.a` (unix) / `qjs.lib` (windows)
dari quickjs.c + quickjs-libc.c memakai compiler host. Cross-compile Android
dipicu lewat env CC/AR yang diset oleh build.py (NDK clang).

Binari CLI qjs/qjsc hanya diunduh untuk platform host yang tersedia di
release resmi (linux/windows/macos x64/arm64).
"""

import os, pathlib, shutil, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common import download as dl, extract as ex, util  # noqa: E402
from common.util import WORK_DIR, log, warn, die  # noqa: E402


def _source(cfg):
    v = cfg["version"]
    repo = cfg.get("repo", "quickjs-ng/quickjs")
    ext = WORK_DIR / "quickjs"
    ext.mkdir(parents=True, exist_ok=True)
    if not (ext / "quickjs.h").is_file():
        p = dl.download(f"https://github.com/{repo}/releases/download/v{v}/quickjs-amalgam.zip",
                        WORK_DIR / "quickjs-amalgam.zip")
        ex.extract_zip(p, ext)
    return ext, v


def build_static_lib(qjs_src, dst_lib, system):
    """Compile amalgam -> libqjs.a / qjs.lib. Return Path atau None bila gagal."""
    is_win = system == "windows"
    cc = os.environ.get("QJS_CC") or os.environ.get("CC") or ("cl" if is_win else "cc")
    ar = os.environ.get("QJS_AR") or ("lib" if is_win else "ar")
    work = WORK_DIR / "qjs-build"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    objs, ok = [], True
    for name in ("quickjs.c", "quickjs-libc.c"):
        srcf = qjs_src / name
        if not srcf.is_file():
            ok = False
            break
        obj = work / (srcf.stem + (".obj" if is_win else ".o"))
        if is_win:
            cmd = [cc, "-c", "/O2", "/MD", f"/I{qjs_src}", str(srcf), f"/Fo{obj}"]
        else:
            cmd = [cc, "-c", "-D_GNU_SOURCE", "-O2", "-std=c11",
                   f"-I{qjs_src}", str(srcf), "-o", str(obj)]
        r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
        if r.returncode != 0:
            warn(f"compile {name} gagal:\n{(r.stdout + r.stderr)[:800]}")
            ok = False
            break
        objs.append(obj)
    if not ok or not objs:
        return None
    if is_win:
        out = dst_lib / "qjs.lib"
        cmd = [ar, f"/OUT:{out}"] + [str(o) for o in objs]
    else:
        out = dst_lib / "libqjs.a"
        cmd = [ar, "rcs", str(out)] + [str(o) for o in objs]
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    shutil.rmtree(work, ignore_errors=True)
    if r.returncode != 0:
        warn("pembuatan libqjs gagal:", (r.stdout + r.stderr)[:400])
        return None
    log("libqjs terbentuk:", out.name)
    return out


def prepare(platform, arch, out_dir, machine=None):
    cfg = util.load_config("versions")["quickjs"]
    qjs_src, v = _source(cfg)
    out = pathlib.Path(out_dir)
    inc, lib, bin_, lic = (out / "include", out / "lib", out / "bin", out / "licenses")
    for d in (inc, lib, bin_, lic):
        d.mkdir(parents=True, exist_ok=True)
    ex.copy_tree(qjs_src, inc / "quickjs")
    files = sorted(x.name for x in qjs_src.iterdir())
    (lic / "LICENSE.quickjs.txt").write_text(
        "QuickJS (quickjs-ng) - MIT license. See https://github.com/quickjs-ng/quickjs\n")

    produced = []
    built = build_static_lib(qjs_src, lib, platform)
    if built:
        produced.append(f"lib/{built.name}")
    else:
        warn("libqjs tidak berhasil dibangun; konsumen bisa compile amalgam sendiri "
             "dari include/quickjs/")

    # binari CLI resmi (host only)
    plat_map = {("linux", "x64"): "linux-x86_64", ("windows", "x64"): "windows-x86_64",
                ("macos", "x64"): "darwin-x86_64", ("macos", "arm64"): "darwin-arm64"}
    key = plat_map.get((platform, machine or arch))
    bins = {}
    if key:
        exe = ".exe" if platform == "windows" else ""
        repo = cfg.get("repo", "quickjs-ng/quickjs")
        for name in ("qjs", "qjsc"):
            try:
                blob = dl.download(
                    f"https://github.com/{repo}/releases/download/v{v}/{name}-{key}{exe}")
                dst = bin_ / (name + exe)
                dst.write_bytes(blob)
                os.chmod(dst, 0o755)
                bins[name] = f"bin/{dst.name}"
                produced.append(f"bin/{dst.name}")
            except Exception as e:
                warn(f"unduh {name}-{key} gagal: {e}")
    else:
        log(f"QuickJS: tidak ada binari CLI resmi untuk ({platform},{machine or arch}).")

    return {"component": "quickjs", "version": v, "kind": "amalgam + static lib",
            "files": produced, "bins": bins, "source_files": files}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", required=True)
    ap.add_argument("--arch", default="x64")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    print(prepare(a.platform, a.arch, a.out))
