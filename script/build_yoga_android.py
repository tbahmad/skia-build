#!/usr/bin/env python3
"""Cross-compile Yoga (libyogacore.a) untuk tiap ABI Android memakai CMake + NDK.

Hasil disalin ke dist/android/lib/<abi>/libyogacore.a agar ikut dipaket
oleh archive_bundle.py. Dipakai oleh workflow build-bundle-android.yml.
"""
import os, pathlib, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_deps as fd

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    abis = [a.strip() for a in os.environ.get("ANDROID_ABIS", "arm64-v8a").split(",") if a.strip()]
    ndk = os.environ.get("ANDROID_NDK_ROOT") or str(ROOT / "android-ndk")
    vers = fd.load_versions()

    # unduh & ekstrak tarball yoga sekali saja
    src = ROOT / "third_party" / "_cache"
    src.mkdir(parents=True, exist_ok=True)
    if not (src / "yoga.tar.gz").exists():
        fd.download(f"https://github.com/facebook/yoga/archive/refs/heads/{vers['yoga'].get('ref','main')}.tar.gz",
                    src / "yoga.tar.gz")
    ext = src / "yoga-src"
    if not ext.exists():
        fd.extract_tar(src / "yoga.tar.gz", ext)
    root = next(ext.iterdir())

    inc_dst = ROOT / "dist" / "android" / "include"
    inc_dst.mkdir(parents=True, exist_ok=True)
    shutil.copytree(root / "yoga", inc_dst / "yoga", dirs_exist_ok=True)

    for abi in abis:
        bld = root / f"build-{abi}"
        args = ["cmake", "-S", str(root), "-B", str(bld),
                f"-DCMAKE_TOOLCHAIN_FILE={os.path.join(ndk,'build','cmake','android.toolchain.cmake')}",
                f"-DANDROID_ABI={abi}", "-DANDROID_PLATFORM=android-21",
                "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_TESTING=OFF",
                "-DCMAKE_POSITION_INDEPENDENT_CODE=ON"]
        fd.sh(args)
        fd.sh(["cmake", "--build", str(bld), "-j", str(os.cpu_count() or 2), "--target", "yogacore"])
        lib = next(iter(bld.glob("**/libyogacore.a")), None)
        if not lib:
            sys.exit(f"ERROR: libyogacore.a tidak terbentuk untuk {abi}")
        dst = ROOT / "dist" / "android" / "lib" / abi
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(lib, dst / lib.name)
        print(f"> yogacore {abi} -> {dst / lib.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
