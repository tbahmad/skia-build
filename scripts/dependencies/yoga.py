#!/usr/bin/env python3
"""Dependency module: Yoga (layout engine Facebook) via CMake.

  * Linux/Windows : build host target `yogacore` -> libyogacore.a / yogacore.lib
  * Android       : cross-compile per ABI memakai NDK toolchain file
                    (ABI diambil dari argumen `abis`)

Hasil dinormalisasi ke nama canonical parana-libs: libyoga.a (unix) / yoga.lib (win).
"""

import os, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common import download as dl, extract as ex, util  # noqa: E402
from common.util import WORK_DIR, log, die  # noqa: E402


def _source():
    cfg = util.load_config("versions")["yoga"]
    ref = cfg.get("ref", "main")
    repo = cfg.get("repo", "facebook/yoga")
    kind = "tags" if ref.startswith("v") else "heads"
    src = WORK_DIR / "yoga"
    tar = src / "yoga.tar.gz"
    ext = src / "src"
    if not ext.exists():
        dl.download(f"https://github.com/{repo}/archive/refs/{kind}/{ref}.tar.gz", tar)
        ex.extract_tar(tar, ext)
    root = next(iter(ext.iterdir()))   # yoga-main/
    return root, f"{ref}-{util.git_short_head(root) or 'tarball'}"


def _headers_and_license(root, out):
    inc, lic = out / "include", out / "licenses"
    inc.mkdir(parents=True, exist_ok=True)
    lic.mkdir(parents=True, exist_ok=True)
    ex.copy_tree(root / "yoga", inc / "yoga")
    lfile = root / "LICENSE"
    if lfile.is_file():
        (lic / "LICENSE.yoga.txt").write_text(lfile.read_text(errors="replace"))


def prepare(platform, arch, out_dir, abis=None, ndk=None):
    out = pathlib.Path(out_dir)
    root, version = _source()
    _headers_and_license(root, out)
    lib = out / "lib"; lib.mkdir(parents=True, exist_ok=True)
    jobs = str(os.cpu_count() or 2)

    if platform == "android":
        produced = []
        for abi in abis or []:
            bld = root / f"build-{abi}"
            tc = os.path.join(ndk, "build", "cmake", "android.toolchain.cmake")
            util.sh(["cmake", "-S", root, "-B", bld, f"-DCMAKE_TOOLCHAIN_FILE={tc}",
                     f"-DANDROID_ABI={abi}", "-DANDROID_PLATFORM=android-21",
                     "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_TESTING=OFF",
                     "-DCMAKE_POSITION_INDEPENDENT_CODE=ON"])
            util.sh(["cmake", "--build", bld, "-j", jobs, "--target", "yogacore"])
            found = next(iter(bld.glob("**/libyogacore.a")), None)
            if not found:
                die(f"libyogacore.a tidak terbentuk untuk {abi}")
            (lib / abi).mkdir(parents=True, exist_ok=True)
            (lib / abi / "libyoga.a").write_bytes(found.read_bytes())
            produced.append(f"lib/{abi}/libyoga.a")
            log(f"yoga {abi} ok")
        return {"component": "yoga", "version": version, "kind": "NDK cross per-ABI",
                "files": produced}

    bld = root / f"build-{platform}"
    util.sh(["cmake", "-S", root, "-B", bld, "-DCMAKE_BUILD_TYPE=Release",
             "-DBUILD_TESTING=OFF", "-DCMAKE_POSITION_INDEPENDENT_CODE=ON"])
    util.sh(["cmake", "--build", bld, "-j", jobs, "--target", "yogacore"])
    if platform == "windows":
        found = next(iter(bld.glob("**/yogacore.lib")), None)
        dst = lib / "yoga.lib"
    else:
        found = next(iter(bld.glob("**/libyogacore.a")), None)
        dst = lib / "libyoga.a"
    if not found:
        die("library yogacore tidak ditemukan setelah build")
    dst.write_bytes(found.read_bytes())
    log(f"yoga {platform}: {dst.name}")
    return {"component": "yoga", "version": version, "kind": "CMake",
            "files": [f"lib/{dst.name}"]}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", required=True)
    ap.add_argument("--arch", default="x64")
    ap.add_argument("--out", required=True)
    ap.add_argument("--abis", default="")
    ap.add_argument("--ndk", default="")
    a = ap.parse_args()
    print(prepare(a.platform, a.arch, a.out,
                  [x.strip() for x in a.abis.split(",") if x.strip()] or None,
                  a.ndk or None))
