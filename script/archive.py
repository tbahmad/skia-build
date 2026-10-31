#!/usr/bin/env python3
"""Kemas hasil build menjadi ZIP dengan struktur rapi siap-pakai untuk development.

Struktur ZIP (sama untuk Linux / Android / Windows):

  include/                 <- seluruh header yang dibutuhkan saat compile
    skia/                  <- public headers + internal headers (SkCanvas, SkRefCnt, dst.)
      core/ ..., modules/ ..., third_party/ ...
  lib/<abi-or-x64>/        <- library statis hasil build (libskia.a, skottie.a, dst.)
  bin/icudtl.dat           <- data ICU (dibutuhkan skia_use_icu)
  LICENSE
  README.txt               <- instruksi singkat link library ke proyek Anda

Hanya binary + header yang diperlukan untuk memakai Skia yang disertakan;
file build (obj, toolchain, test binaries) tidak ikut masuk arsip.
"""

import argparse, os, pathlib, platform, re, sys, zipfile

# modul esensial yang kita build (harus konsisten dengan script/build.py)
MODULES = ["skia", "skottie", "skparagraph", "skshaper", "svg"]

# pola nama file library per sistem: di Linux/Android -> lib<mod>.a ; Windows -> <mod>.lib
LIB_SUFFIX = {"linux": ".a", "android": ".a", "windows": ".lib"}


def find_libs(out_dir, system):
    """Cari library statis modul esensial + dependency bundled di direktori out."""
    suffix = LIB_SUFFIX[system]
    libs = []
    for p in sorted(pathlib.Path(out_dir).glob("*" + suffix)):
        name = p.name
        # selalu sertakan modul utama
        base = name.lstrip("lib").replace(suffix, "")
        if base in MODULES:
            libs.append(p)
            continue
        # dependency bundled yang ditautkan oleh libskia (perlu saat final link)
        dep_prefixes = ("expat", "freetype", "harfbuzz", "icu", "jpeg", "png",
                        "webp", "z", "sfntly")
        if any(base.startswith(d) or base == d for d in dep_prefixes):
            libs.append(p)
    return libs


def collect_headers(skia):
    """Kumpulkan header publik + internal yang saling me-#include via path 'src/...'."""
    patterns = [
        "include/**/*.h",
        "include/private/*.h",
        "modules/particles/include/*.h",
        "modules/skottie/include/*.h",
        "modules/skottie/src/**/*.h",
        "modules/skparagraph/include/*.h",
        "modules/skplaintexteditor/include/*.h",
        "modules/skresources/include/*.h",
        "modules/sksg/include/*.h",
        "modules/skshaper/include/*.h",
        "modules/skshaper/src/*.h",
        "modules/svg/include/*.h",
        # internal headers WAJIB: public header meng-#include "src/core/Sk*.h"
        "src/**/*.h",
        # header dependency bundled yang terekspos lewat include publik
        "third_party/externals/freetype/include/**/*.h",
        "third_party/externals/harfbuzz/src/**/*.h",
        "third_party/externals/icu/source/common/**/*.h",
        "third_party/externals/icu/source/i18n/**/*.h",
        "third_party/externals/libpng/*.h",
        "third_party/externals/libwebp/src/**/*.h",
        "third_party/externals/zlib/*.h",
        "third_party/externals/expat/**/*.h",
    ]
    seen = set()
    result = []
    skia_path = pathlib.Path(skia)
    for pat in patterns:
        for p in skia_path.glob(pat):
            if not p.is_file():
                continue
            rel = str(p.relative_to(skia_path))
            if rel in seen:
                continue
            seen.add(rel)
            result.append((rel, p))
    return result


README_TMPL = """Skia {version} - {system}/{arch} ({build_type})
========================================================

Isi paket:
  include/skia/   seluruh header (public + internal + dependency bundled)
  lib/{arch}/     library statis: {libs}
  bin/icudtl.dat  data ICU (muat sekali saat startup bila memakai SkUnicode)

Cara pakai (compile & link):
  CXXFLAGS += -I<path-ekstrak>/include/skia
  LDFLAGS  += -L<path-ekstrak>/lib/{arch} -lskia \\
              -lskottie -lskparagraph -lskshaper -lsvg \\
              (urutkan dari modul tertinggi ke dependency)

Linux/Android contoh lengkap:
  g++ app.cpp -I$SKIA_DIR/include/skia $SKIA_DIR/lib/{arch}/libskia.a \\
      $SKIA_DIR/lib/{arch}/lib{mods}.a -lpthread -ldl -o app

Windows (MSVC):
  cl app.cpp /I<dir>\\include\\skia /link /LIBPATH:<dir>\\lib\\x64 skia.lib ...

Catatan:
  - Header internal (src/) disertakan karena public header Skia
    meng-#include path "src/core/...". Jangan hapus folder tersebut.
  - Generated header (modules/skvm) sudah termasuk di source tree m158.

Dukungan GPU (build ini AKTIF):
  Backend yang ter-compile ke dalam libskia.a:
    * OpenGL / OpenGL ES  -> include/skia/include/gpu/gl/ (SkGLBackend.h, dsk)
    * EGL wrapper         -> include/skia/include/gpu/gl/ (SkEGLImageBackend.h)
                             [AKTIF di Linux & Android; di Windows GL memakai
                              WGL native / D3D, jadi tidak ada wrapper EGL]
    * Vulkan              -> include/skia/include/gpu/vk/  (linux/android/windows AKTIF di build ini)
    * Direct3D            -> include/skia/include/gpu/d3d/ (windows)
    * Metal               -> include/skia/include/gpu/mtl/ (macos)
  (* sesuai platform build masing-masing; daftar lengkap lihat args gn di log)

  Contoh minimal render GL (Linux):
    #include "include/core/SkSurface.h"
    #include "include/gpu/GpuTypes.h"
    #include "include/gpu/GrDirectContext.h"
    #include "include/gpu/gl/GrGLInterface.h"
    ...
    auto ctx = GrDirectContexts::MakeGL(GrGLInterfaces::MakeNative());
  Contoh minimal render Vulkan:
    #include "include/gpu/vk/VulkanBackend.h"
    #include "include/gpu/vk/GrVkBackendContext.h"
    ...
    auto ctx = GrDirectContexts::MakeVulkan(backend_context, options);
  Link tambahan saat final link aplikasi (library sistem, BUKAN dari zip):
    Linux   : -lGL -lEGL -lvulkan   (libgl1-mesa-dev / libegl1-mesa-dev / libvulkan1)
    Android : -lGLESv2 -lEGL -lvulkan (CMake NDK: find_library GLESv2 EGL vulkan)
    Windows : opengl32.lib + vulkan-1.lib (GL via WGL native; Vulkan bundled;
              atau backend Direct3D11 -> d3d11.lib dxgi.lib)
"""


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
    # pada workflow Android, platform tetap Linux tapi artefaknya android per-ABI
    if os.environ.get("SKIA_TARGET_OS") == "android":
        system = "android"

    build_type = args.build_type
    machine = args.machine

    head = ""
    try:
        import subprocess
        head = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()[:10]
    except Exception:
        pass
    m = re.search(r"m(\d+)", args.version)
    version = f"m{m.group(1)}-{head}" if (m and head) else (args.version.replace("/", "_") +
                                                            ("-" + head if head else ""))
    version = version.replace("/", "_")

    # --- tentukan direktori out per platform ----------------------------------
    if system == "android":
        abi = os.environ.get("ANDROID_ABI", "arm64-v8a")
        out_dir = pathlib.Path("out") / f"{build_type}-{abi}"
        arch_name = abi
    else:
        out_dir = pathlib.Path("out") / f"{build_type}-{machine}"
        arch_name = machine

    if not out_dir.is_dir():
        print(f"ERROR: direktori out tidak ditemukan: {out_dir}", file=sys.stderr)
        return 1

    libs = find_libs(out_dir, system)
    if not libs:
        print(f"ERROR: tidak ada library statis di {out_dir}", file=sys.stderr)
        return 1

    headers = collect_headers(skia)
    print(f"> Menemukan {len(libs)} library dan {len(headers)} header di {out_dir}")

    target = os.path.join(root, f"Skia-{version}-{system}-{arch_name}-{build_type}.zip")
    print("> Writing", target)

    n = 0
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1) header -> include/skia/<path asli di repo skia>
        for rel, p in headers:
            zf.write(str(p), f"include/skia/{rel}")
            n += 1

        # 2) library -> lib/<arch>/
        for p in libs:
            zf.write(str(p), f"lib/{arch_name}/{p.name}")
            n += 1

        # 3) icudtl.dat -> bin/
        icu = out_dir / "icudtl.dat"
        if icu.is_file():
            zf.write(str(icu), "bin/icudtl.dat")
            n += 1

        # 4) LICENSE
        lic = pathlib.Path("LICENSE")
        if lic.is_file():
            zf.write(str(lic), "LICENSE")
            n += 1

        # 5) README.txt singkat cara pakai
        mods = " ".join(f"-l{m_}" for m_ in MODULES if m_ != "skia")
        zf.writestr("README.txt",
                    README_TMPL.format(version=version, system=system, arch=arch_name,
                                       build_type=build_type,
                                       libs=", ".join(p.name for p in libs), mods=mods.strip()))
        n += 1

    print(f"> {n} files archived -> {os.path.basename(target)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
