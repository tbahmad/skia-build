#!/usr/bin/env python3
"""Kemas hasil build Android menjadi zip (gaya archive.py JetBrains, di-update).

Menyertakan per ABI:
  - libskia.a gabungan (obj/libskia.a) atau semua *.a di out/<type>-<abi>/
  - icudtl.dat (bila ada)
Seluruh public headers disertakan sekali (tidak per-ABI).

Nama file: Skia-<versi>-android-<tipe>.zip  (karakter '/' disanitasi '_')
"""

import argparse, os, pathlib, re, subprocess, sys, zipfile

DEFAULT_ABIS = ["arm64-v8a", "armeabi-v7a", "x86_64"]


def parents(path):
    res = []
    parent = path.parent
    while "." != str(parent):
        res.insert(0, parent)
        parent = parent.parent
    return res


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

    # versi konkret dengan sha HEAD; sanitasi '/' -> '_'
    head = ""
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()[:10]
    except Exception:
        pass
    m = re.match(r"^m(\d+)", args.version)
    version = f"m{m.group(1)}-{head}" if (m and head) else (args.version + ("-" + head if head else ""))
    version = version.replace("/", "_")

    header_globs = [
        "include/**/*",
        "modules/particles/include/*.h",
        "modules/skottie/include/*.h",
        "modules/skottie/src/*.h",
        "modules/skottie/src/animator/*.h",
        "modules/skottie/src/effects/*.h",
        "modules/skottie/src/layers/*.h",
        "modules/skottie/src/layers/shapelayer/*.h",
        "modules/skottie/src/text/*.h",
        "modules/skparagraph/include/*.h",
        "modules/skplaintexteditor/include/*.h",
        "modules/skresources/include/*.h",
        "modules/sksg/include/*.h",
        "modules/skshaper/include/*.h",
        "modules/skshaper/src/*.h",
        "modules/svg/include/*.h",
        "src/core/*.h",
        "src/gpu/gl/*.h",
        "src/utils/*.h",
        "third_party/externals/freetype/include/**/*",
        "third_party/externals/harfbuzz/src/*.h",
        "third_party/externals/icu/source/common/**/*.h",
        "third_party/externals/libpng/*.h",
        "third_party/externals/libwebp/src/**/*.h",
        "third_party/externals/zlib/*.h",
        "LICENSE",
    ]

    target = os.path.join(root, f"Skia-{version}-android-{args.build_type}.zip")
    print("> Writing", target)

    n = 0
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        dirs = set()

        def add(path):
            nonlocal n
            p = pathlib.Path(path)
            if not p.is_file():
                return
            for d in parents(p):
                if d not in dirs:
                    zf.write(str(d))
                    dirs.add(d)
            zf.write(str(p))
            n += 1

        # library & data per ABI
        found_any = False
        for abi in abis:
            out_dir = f"out/{args.build_type}-{abi}"
            combined = os.path.join(out_dir, "obj", "libskia.a")
            if os.path.exists(combined):
                zf.write(combined, f"libs/{abi}/libskia.a")
                n += 1
                found_any = True
            else:
                for a in sorted(pathlib.Path(out_dir).glob("*.a")):
                    zf.write(str(a), f"libs/{abi}/{a.name}")
                    n += 1
                    found_any = True
            icu = os.path.join(out_dir, "icudtl.dat")
            if os.path.exists(icu):
                zf.write(icu, f"res/{abi}/icudtl.dat")
                n += 1
        if not found_any:
            sys.exit(f"ERROR: tidak ada library hasil build di out/{args.build_type}-<abi>/. "
                     f"Jalankan build_android.py dulu.")

        # headers (sekali saja)
        for g in header_globs:
            for path in pathlib.Path().glob(g):
                add(path)

    print(f"> {n} files archived")
    return 0


if __name__ == "__main__":
    sys.exit(main())
