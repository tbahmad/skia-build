#!/usr/bin/env python3
"""Kemas hasil build Android menjadi ZIP dengan struktur rapi siap-pakai.

Struktur ZIP:

  include/skia/            <- seluruh header (public + internal + dependency bundled)
  lib/<abi>/               <- library statis per ABI (arm64-v8a, armeabi-v7a, x86_64)
  bin/icudtl.dat           <- data ICU (sekali saja; ABI-independen)
  LICENSE
  README.txt               <- instruksi singkat integrasi ke proyek Android (CMake/NDK)

Nama file: Skia-<versi>-android-<tipe>.zip ('/' disanitasi '_').
"""

import argparse, os, pathlib, re, subprocess, sys, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from archive import MODULES, collect_headers  # noqa: E402  (pakai logika yang sama)

DEFAULT_ABIS = ["arm64-v8a", "armeabi-v7a", "x86_64"]


def find_libs_for_abi(out_dir):
    """Semua *.a modul esensial + dependency bundled di out/<type>-<abi>/."""
    libs = []
    for p in sorted(pathlib.Path(out_dir).glob("*.a")):
        base = p.name.lstrip("lib").replace(".a", "")
        if base in MODULES:
            libs.append(p)
            continue
        dep_prefixes = ("expat", "freetype", "harfbuzz", "icu", "jpeg", "png",
                        "webp", "z", "sfntly")
        if any(base.startswith(d) or base == d for d in dep_prefixes):
            libs.append(p)
    return libs


README_TMPL = """Skia {version} - Android ({build_type})
========================================================

Isi paket:
  include/skia/   seluruh header (public + internal + dependency bundled)
  lib/<abi>/      library statis per ABI: {abis}
  bin/icudtl.dat  data ICU (copy ke assets/ bila memakai SkUnicode)

Integrasi CMake (Android NDK):
  set(SKIA_DIR ${{CMAKE_SOURCE_DIR}}/third_party/skia)
  target_include_directories(app PRIVATE ${{SKIA_DIR}}/include/skia)
  target_link_libraries(app PRIVATE
    ${{SKIA_DIR}}/lib/${{ANDROID_ABI}}/libskia.a
    ${{SKIA_DIR}}/lib/${{ANDROID_ABI}}/libskottie.a   # dst. per modul
    jnigraphics log android)

Catatan:
  - Header internal (src/) disertakan karena public header Skia
    meng-#include path "src/core/...". Jangan hapus folder tersebut.
  - Link library dari modul tertinggi ke dependency (skottie -> skia -> deps).

Dukungan GPU (build ini AKTIF):
  Backend OpenGL ES + EGL sudah ter-compile ke dalam libskia.a per ABI.
  Header: include/skia/include/gpu/gl/ (SkGLBackend.h, GrGLInterface, EGL).
  Vulkan sengaja OFF di Android build ini.
  Tautkan library sistem GL saat final link aplikasi:
    target_link_libraries(app PRIVATE GLESv2 EGL)   # CMake/NDK
  Contoh: GrDirectContexts::MakeGL(GrGLInterfaces::MakeNative())
        -> include/gpu/GrDirectContext.h + include/gpu/gl/GrGLInterface.h
"""


def main():
    os.chdir(os.path.join(os.path.dirname(__file__), os.pardir))
    root = os.getcwd()
    skia = os.path.join(root, "skia")
    os.chdir(skia)

    parser = argparse.ArgumentParser()
    parser.add_argument("--build-type", default=os.environ.get("BUILD_TYPE", "Release"))
    parser.add_argument("--version", default=os.environ.get("SKIA_VERSION", "main"))
    parser.add_argument("--abis", default=os.environ.get("ANDROID_ABIS", ",".join(DEFAULT_ABIS)))
    args = parser.parse_args()
    abis = [a.strip() for a in args.abis.split(",") if a.strip()]

    head = ""
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()[:10]
    except Exception:
        pass
    m = re.search(r"m(\d+)", args.version)
    version = f"m{m.group(1)}-{head}" if (m and head) else \
        (args.version.replace("/", "_") + ("-" + head if head else ""))
    version = version.replace("/", "_")

    # kumpulkan library per ABI
    abi_libs = {}
    for abi in abis:
        out_dir = pathlib.Path("out") / f"{args.build_type}-{abi}"
        if not out_dir.is_dir():
            print(f"> SKIP ABI {abi}: {out_dir} tidak ada")
            continue
        libs = find_libs_for_abi(out_dir)
        if libs:
            abi_libs[abi] = libs

    if not abi_libs:
        print(f"ERROR: tidak ada library hasil build di out/{args.build_type}-<abi>/. "
              f"Jalankan build_android.py dulu.", file=sys.stderr)
        return 1

    headers = collect_headers(skia)
    print(f"> ABI terarsip: {', '.join(abi_libs)} | {len(headers)} header")

    target = os.path.join(root, f"Skia-{version}-android-{args.build_type}.zip")
    print("> Writing", target)

    n = 0
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1) header -> include/skia/
        for rel, p in headers:
            zf.write(str(p), f"include/skia/{rel}")
            n += 1

        # 2) library per ABI -> lib/<abi>/
        for abi, libs in abi_libs.items():
            for p in libs:
                zf.write(str(p), f"lib/{abi}/{p.name}")
                n += 1

        # 3) icudtl.dat (cari di ABI pertama yang punya) -> bin/
        for abi in abi_libs:
            icu = pathlib.Path("out") / f"{args.build_type}-{abi}" / "icudtl.dat"
            if icu.is_file():
                zf.write(str(icu), "bin/icudtl.dat")
                n += 1
                break

        # 4) LICENSE
        lic = pathlib.Path("LICENSE")
        if lic.is_file():
            zf.write(str(lic), "LICENSE")
            n += 1

        # 5) README.txt
        zf.writestr("README.txt",
                    README_TMPL.format(version=version, build_type=args.build_type,
                                       abis=", ".join(abi_libs)))
        n += 1

    print(f"> {n} files archived -> {os.path.basename(target)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
