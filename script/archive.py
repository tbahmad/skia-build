#!/usr/bin/env python3
"""Kemas hasil build + header menjadi zip (adaptasi script/archive.py JetBrains/skia-build).

Menyertakan:
  - library statis (*.a / *.lib) dan icudtl.dat dari direktori out/
  - seluruh public headers (include/, src/*.h, modul, third_party yang di-bundle)
  - file LICENSE agar artefak siap didistribusikan
"""

import argparse, os, pathlib, platform, re, sys, zipfile


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
    parser.add_argument("--machine", default={"AMD64": "x64", "x86_64": "x64",
                                              "arm64": "arm64"}.get(platform.machine(), "x64"))
    args = parser.parse_args()

    system = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}[platform.system()]
    build_type = args.build_type
    machine = args.machine

    # versi konkret: mNNN-<sha HEAD 10 karakter pertama> bila memungkinkan
    head = ""
    try:
        import subprocess
        head = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()[:10]
    except Exception:
        pass
    m = re.match(r"^m(\d+)", args.version)
    version = f"m{m.group(1)}-{head}" if (m and head) else (args.version + ("-" + head if head else ""))
    # nama file tidak boleh mengandung "/" (mis. ref "chrome/m148") -> ganti dengan "_"
    version = version.replace("/", "_")

    out_dir = "out/" + build_type + "-" + machine
    globs = [
        out_dir + "/*.a",
        out_dir + "/*.lib",
        out_dir + "/icudtl.dat",
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
        # src/**/*.h diperlukan public header (mis. SkRefCnt, SkTArray) yang
        # meng-#include "src/core/Sk*.h" -> wajib disertakan agar ZIP siap compile.
        "src/**/*.h",
        "third_party/externals/freetype/include/**/*",
        "third_party/externals/harfbuzz/src/*.h",
        "third_party/externals/icu/source/common/**/*.h",
        "third_party/externals/libpng/*.h",
        "third_party/externals/libwebp/src/**/*.h",
        "third_party/externals/zlib/*.h",
        "LICENSE",
    ]

    target = os.path.join(root, f"Skia-{version}-{system}-{build_type}-{machine}.zip")
    print("> Writing", target)

    n = 0
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        dirs = set()
        for glob in globs:
            for path in pathlib.Path().glob(glob):
                if not path.is_file():
                    continue
                for d in parents(path):
                    if d not in dirs:
                        zf.write(str(d))
                        dirs.add(d)
                zf.write(str(path))
                n += 1

    print(f"> {n} files archived")
    return 0


if __name__ == "__main__":
    sys.exit(main())
