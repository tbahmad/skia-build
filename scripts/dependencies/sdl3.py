#!/usr/bin/env python3
"""Dependency module: SDL3.

Sumber resmi release libsdl-org/SDL (versi dari config/versions.json):
  * Windows MSVC -> SDL3-devel-<v>-VC.zip   (SDL3.lib + SDL3.dll + include/)
  * Linux        -> source tarball, build CMake SDL3-static
  * Android      -> SDL3-devel-<v>-android.zip (aar; libSDL3.so per ABI + JNI)

API: prepare(platform, arch, out_dir) -> dict staging layout parana-libs:
  <out>/include/SDL3/...
  <out>/lib/<file>            (linux/windows)
  <out>/lib/<abi>/libSDL3.so  (android)
  <out>/bin/SDL3.dll          (windows runtime)
  <out>/licenses/LICENSE.SDL3.txt
"""

import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common import download as dl, extract as ex, util  # noqa: E402
from common.util import WORK_DIR, log, warn, die  # noqa: E402


def _base_url(v):
    repo = v.get("repo", "libsdl-org/SDL")
    tag = v.get("tag", f"release-{v['version']}")
    return f"https://github.com/{repo}/releases/download/{tag}"


def prepare(platform, arch, out_dir, abi=None):
    ver = util.load_config("versions")["sdl3"]
    v = ver["version"]
    src = WORK_DIR / "sdl3"
    src.mkdir(parents=True, exist_ok=True)
    out = pathlib.Path(out_dir)
    inc, lib, bin_, lic = (out / "include", out / "lib", out / "bin", out / "licenses")
    for d in (inc, lib, bin_, lic):
        d.mkdir(parents=True, exist_ok=True)

    if platform == "android":
        p = dl.download(f"{_base_url(ver)}/SDL3-devel-{v}-android.zip", src / "SDL3-android.zip")
        aar_dir = ex.extract_zip(p, src / "aar"); aar_dir = next(aar_dir.glob("*.aar"))
        ex2 = ex.extract_zip(aar_dir, src / "aar-content")
        inc_root = ex2 / "include"
        jni = list((ex2 / "jni").glob("**/*.so")) if (ex2 / "jni").is_dir() else []
        for so in jni:
            abi_name = so.parent.name
            (lib / abi_name).mkdir(parents=True, exist_ok=True)
            (lib / abi_name / so.name).write_bytes(so.read_bytes())
        license_file = ex2 / "LICENSE.txt" if (ex2 / "LICENSE.txt").is_file() \
            else src / "aar-extract" / "LICENSE.txt"
        ex.copy_tree(inc_root, inc / "SDL3")
        if license_file.is_file():
            (lic / "LICENSE.SDL3.txt").write_text(license_file.read_text(errors="replace"))
        abis = sorted({p_.parent.name for p_ in jni})
        log(f"SDL3 {v} android: .so per ABI {abis}")
        return {"component": "sdl3", "version": v, "kind": "aar (shared .so + JNI)",
                "abis": abis, "files": [f"lib/{a}/libSDL3.so" for a in abis]}

    if platform == "windows":
        p = dl.download(f"{_base_url(ver)}/SDL3-devel-{v}-VC.zip", src / "SDL3-VC.zip")
        root = next(iter(ex.extract_zip(p, src / "vc").iterdir()))   # SDL3-<v>/
        libx = root / "lib" / "x64"
        ex.copy_tree(root / "include" / "SDL3", inc / "SDL3")
        (lib / "SDL3.lib").write_bytes((libx / "SDL3.lib").read_bytes())
        (bin_ / "SDL3.dll").write_bytes((libx / "SDL3.dll").read_bytes())
        (lic / "LICENSE.SDL3.txt").write_text((root / "LICENSE.txt").read_text(errors="replace"))
        log(f"SDL3 {v} windows VC: SDL3.lib + SDL3.dll")
        return {"component": "sdl3", "version": v, "kind": "MSVC devel zip",
                "files": ["lib/SDL3.lib", "bin/SDL3.dll"]}

    if platform == "linux":
        p = dl.download(f"{_base_url(ver)}/SDL3-{v}.tar.gz", src / f"SDL3-{v}.tar.gz")
        root = next(iter(ex.extract_tar(p, src / "src").iterdir()))  # SDL3-<v>/
        bld = root / "build"
        jobs = str(__import__("os").cpu_count() or 2)
        util.sh(["cmake", "-S", root, "-B", bld,
                 "-DCMAKE_BUILD_TYPE=Release", "-DSDL_STATIC=ON", "-DSDL_SHARED=OFF",
                 "-DSDL_TESTS=OFF", "-DSDL_EXAMPLES=OFF", "-DSDL_JPEG=OFF",
                 "-DSDL_VULKAN=ON", "-DSDL_OPENGL=ON"])
        util.sh(["cmake", "--build", bld, "-j", jobs, "--target", "SDL3-static"])
        found = next(iter(bld.glob("**/libSDL3.a")), None)
        if not found:
            die("libSDL3.a tidak ditemukan setelah build SDL3")
        ex.copy_tree(root / "include" / "SDL3", inc / "SDL3")
        (lib / "libSDL3.a").write_bytes(found.read_bytes())
        (lic / "LICENSE.SDL3.txt").write_text((root / "LICENSE.txt").read_text(errors="replace"))
        log(f"SDL3 {v} linux static: libSDL3.a")
        return {"component": "sdl3", "version": v, "kind": "CMake static build",
                "files": ["lib/libSDL3.a"]}

    die(f"platform tidak didukung untuk SDL3: {platform}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", required=True)
    ap.add_argument("--arch", default="x64")
    ap.add_argument("--out", required=True)
    r = prepare(ap.parse_args().platform, ap.parse_args().arch, ap.parse_args().out)
    print(r)
