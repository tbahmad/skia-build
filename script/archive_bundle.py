#!/usr/bin/env python3
"""Gabungkan hasil build Skia + SDL3 + Yoga + QuickJS menjadi SATU arsip .tar.gz.

Dipakai SETELAH:
  script/checkout.py        -> skia/ ter-clone
  script/build*.py          -> skia/out/<type>-<arch|abi>/ berisi libskia.a dkk
  script/fetch_deps.py      -> dist/<platform>/ berisi include+lib SDL3/yoga/quickjs

Struktur arsip bundle (prefix <bundle-name>/):

  include/skia/     header Skia (public + internal src/ + third_party bundled)
  include/SDL3/     header SDL3
  include/yoga/     header Yoga (pakai #include "yoga/YGNode.h")
  include/quickjs/  header + sumber amalgam QuickJS
  lib/<arch-or-abi>/  libskia.a, modul skia, deps bundled, libSDL3*, yogacore,
                      libquickjs.a (bila di-build), SDL3.dll / *.so runtime
  bin/              icudtl.dat, qjs, qjsc (sesuai platform)
  licenses/         LICENSE tiap komponen
  versions.json     daftar versi seluruh komponen
  README.txt        instruksi compile/link & contoh pakai SDL3+Skia

Nama file: prana-libs-<platform>-<arch>.tar.gz
  (Android: prana-libs-android.tar.gz — berisi seluruh ABI di dalam lib/<abi>/)
"""

import argparse, io, json, os, pathlib, platform, re, shutil, subprocess, sys, tarfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from archive import MODULES, collect_headers, LIB_SUFFIX   # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


def bundle_name(system, archs):
    """prana-libs-<platform>-<arch>.tar.gz ; Android tidak pakai suffix arch."""
    if system == "android":
        return f"prana-libs-android.tar.gz"
    arch = archs[0] if len(archs) == 1 else "+".join(sorted(archs))
    return f"prana-libs-{system}-{arch}.tar.gz"


def find_skia_libs(out_dir, system):
    """Library statis modul esensial + dependency bundled (logika sama dgn archive.py)."""
    suffix = LIB_SUFFIX.get(system, ".a")
    libs = []
    for p in sorted(pathlib.Path(out_dir).glob("*" + suffix)):
        base = p.name.lstrip("lib").replace(suffix, "")
        if base in MODULES:
            libs.append(p)
            continue
        dep_prefixes = ("expat", "freetype", "harfbuzz", "icu", "jpeg", "png",
                        "webp", "z", "sfntly")
        if any(base.startswith(d) or base == d for d in dep_prefixes):
            libs.append(p)
    return libs


def quickjs_static_lib(qjs_inc, out_dir, system):
    """Build libquickjs.a dari amalgam resmi quickjs-ng memakai compiler host.

    Amalgam = semua .c digabung; tinggal compile 1 TU + quickjs-libc.c.
    Bila gagal (mis. cross-compile tanpa toolchain mudah), kembalikan None —
    pengguna tetap bisa meng-#include .c sendiri.
    """
    if not qjs_inc.is_dir():
        return None
    import platform as _pf
    cc = os.environ.get("CC") or ("cl" if _pf.system() == "Windows" else "cc")
    work = ROOT / "_quickjs_build"
    work.mkdir(exist_ok=True)
    objs = []
    ok = True
    for name in ("quickjs.c", "quickjs-libc.c"):
        src = qjs_inc / name
        if not src.is_file():
            ok = False
            break
        obj = work / (src.stem + (".obj" if _pf.system() == "Windows" else ".o"))
        if _pf.system() == "Windows":
            cmd = [cc, "-c", "/O2", "/MD", "/I" + str(qjs_inc), str(src), "/Fo" + str(obj)]
        else:
            cmd = [cc, "-c", "-D_GNU_SOURCE", "-O2", "-I", str(qjs_inc), str(src), "-o", str(obj)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"WARNING: compile {name} gagal:\n{r.stderr[:800]}")
            ok = False
            break
        objs.append(obj)
    if not ok or not objs:
        shutil.rmtree(work, ignore_errors=True)
        return None
    lib = out_dir / ("quickjs.lib" if _pf.system() == "Windows" else "libquickjs.a")
    if _pf.system() == "Windows":
        r = subprocess.run(["lib", "/OUT:" + str(lib), *[str(o) for o in objs]],
                           capture_output=True, text=True, shell=True)
    else:
        r = subprocess.run(["ar", "rcs", str(lib), *[str(o) for o in objs]],
                           capture_output=True, text=True)
    shutil.rmtree(work, ignore_errors=True)
    if r.returncode != 0:
        print("WARNING: pembuatan libquickjs.a gagal:", r.stderr[:400])
        return None
    print("> libquickjs.a berhasil dibuat:", lib)
    return lib


README_TMPL = """Skia Bundle {version} - {system}/{arch} ({build_type})
========================================================

Komponen (lihat versions.json):
  * Skia      : rendering engine 2D (GPU GL/EGL/Vulkan/D3D sesuai platform)
  * SDL3      : windowing/input/audio             ({sdl})
  * Yoga      : layout engine flexbox (React-Native style) ({yoga})
  * QuickJS   : JavaScript engine ringan          ({qjs})

Isi paket:
  include/skia/     seluruh header Skia (public + internal src/ + deps bundled)
  include/SDL3/     header SDL3           -> #include <SDL3/SDL.h>
  include/yoga/     header Yoga           -> #include "yoga/YGNode.h"
                    (tambahkan -I<dir>/include agar path 'yoga/...' resolve)
  include/quickjs/  header + amalgam QuickJS -> #include "quickjs.h"
                    (-I<dir>/include/quickjs); libquickjs.a sudah disediakan
                    bila build-nya sukses, kalau tidak: compile quickjs.c Anda sendiri.
  lib/{arch}/       libskia.a + modul + deps bundled + libSDL3* + yogacore + quickjs
  bin/              icudtl.dat, qjs/qjsc (CLI interpreter & bytecode compiler)
  licenses/         lisensi tiap komponen

Compile & link (Linux contoh lengkap, aplikasi SDL3 + Skia CPU/GPU):
  g++ app.cpp -std=c++17 -frtti \
      -I$SKIA_DIR/include/skia -I$SKIA_DIR/include -I$SKIA_DIR/include/quickjs \
      $SKIA_DIR/lib/{arch}/libskia.a $SKIA_DIR/lib/{arch}/libskottie.a \
      $SKIA_DIR/lib/{arch}/libskparagraph.a $SKIA_DIR/lib/{arch}/libskshaper.a \
      $SKIA_DIR/lib/{arch}/libsvg.a \
      $SKIA_DIR/lib/{arch}/lib<deps-bundled>.a \
      $SKIA_DIR/lib/{arch}/libSDL3.a $SKIA_DIR/lib/{arch}/libyogacore.a \
      $SKIA_DIR/lib/{arch}/libquickjs.a \
      -lGL -lEGL -lvulkan -lSDL3 -lpthread -ldl -lm -lrt -o app

  Catatan SDL3-static Linux: butuh pkg-config sistem saat final link
  (libx11-dev dll.) atau gunakan SDL3 shared dari distro dan cukup -lSDL3.

Windows (MSVC):
  cl app.cpp /std:c++17 /EHsc /I<dir>\\include\\skia /I<dir>\\include ^
     /I<dir>\\include\\quickjs ^
     /link /LIBPATH:<dir>\\lib\\x64 skia.lib SDL3.lib yogacore.lib quickjs.lib ...
  SDL3.dll ada di bin/ -> salin ke folder exe aplikasi.

Android (NDK, CMake):
  target_include_directories(app PRIVATE
    ${{SKIA_DIR}}/include/skia ${{SKIA_DIR}}/include ${{SKIA_DIR}}/include/quickjs)
  target_link_libraries(app PRIVATE
    ${{SKIA_DIR}}/lib/${{ANDROID_ABI}}/libskia.a ... 
    ${{SKIA_DIR}}/lib/${{ANDROID_ABI}}/libyogacore.a
    GLESv2 EGL log android)   # + salin libSDL3.so dari aar SDL3 bila dipakai

Contoh cepat (SDL3 window + Skia canvas):
  #include <SDL3/SDL.h>
  #include "include/core/SkCanvas.h"
  #include "include/core/SkSurface.h"
  ...
  SDL_Window* w; SDL_Renderer* r;
  SDL_CreateWindowAndRenderer("hello", 512, 512, 0, &w, &r);
  auto surf = SkSurfaces::Raster(SkImageInfo::MakeN32Premul(512, 512));
  surf->getCanvas()->clear(SK_ColorBLUE);
  // upload surf->pixels() ke SDL_Texture lalu render.
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-type", default=os.environ.get("BUILD_TYPE", "Release"))
    parser.add_argument("--version", default=os.environ.get("SKIA_VERSION", "main"),
                        help="ref/versi Skia (untuk nama file)")
    parser.add_argument("--machine", default={"AMD64": "x64", "x86_64": "x64",
                                              "arm64": "arm64"}.get(platform.machine(), "x64"))
    parser.add_argument("--abis", default=os.environ.get("ANDROID_ABIS", ""),
                        help="Android saja: daftar ABI pisah koma")
    args = parser.parse_args()

    system = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}[platform.system()]
    if os.environ.get("SKIA_TARGET_OS") == "android":
        system = "android"

    skia = ROOT / "skia"
    dist = ROOT / "dist"

    # --- tentukan direktori out Skia per platform -----------------------------
    skia_outs = {}   # arch_label -> Path
    if system == "android":
        for abi in [a.strip() for a in args.abis.split(",") if a.strip()]:
            od = skia / "out" / f"{args.build_type}-{abi}"
            if od.is_dir():
                skia_outs[abi] = od
    else:
        od = skia / "out" / f"{args.build_type}-{args.machine}"
        if od.is_dir():
            skia_outs[args.machine] = od
    if not skia_outs:
        sys.exit("ERROR: direktori out Skia tidak ditemukan; jalankan build dulu.")

    # --- dist dependency -------------------------------------------------------
    deps_dirs = [d for d in ([dist / system] if (dist / system).is_dir() else [])]
    if system == "linux" and (dist / "linux-android").is_dir():
        pass  # android punya workflow sendiri; tidak digabung ke linux
    if not deps_dirs:
        print("WARNING: dist/ kosong; bundle hanya berisi Skia "
              "(jalankan script/fetch_deps.py untuk menyertakan SDL3/yoga/quickjs)")
    deps_dir = deps_dirs[0] if deps_dirs else None

    vers = json.loads((ROOT / "third_party" / "versions.json").read_text())

    # --- kumpulkan isi ---------------------------------------------------------
    entries = []          # (arcname, Path)
    infos = {}

    head = ""
    try:
        head = subprocess.check_output(["git", "-C", str(skia), "rev-parse", "HEAD"]).decode().strip()[:10]
    except Exception:
        pass
    m = re.search(r"m(\d+)", args.version)
    skia_version = f"m{m.group(1)}-{head}" if (m and head) else \
        args.version.replace("/", "_") + ("-" + head if head else "")
    skia_version = skia_version.replace("/", "_")

    # 1) header skia -> include/skia/
    headers = collect_headers(str(skia))
    for rel, p in headers:
        entries.append((f"include/skia/{rel}", pathlib.Path(p)))

    # 2) library skia per arch/abi -> lib/<arch>/
    all_libs = {}
    for label, od in skia_outs.items():
        libs = find_skia_libs(od, system)
        all_libs[label] = libs
        for p in libs:
            entries.append((f"lib/{label}/{p.name}", p))
        icu = od / "icudtl.dat"
        if icu.is_file():
            entries.append(("bin/icudtl.dat", icu))
    n_libs = sum(len(v) for v in all_libs.values())
    print(f"> Skia: {len(headers)} header, {n_libs} library ({', '.join(skia_outs)})")

    # 3) dependency (SDL3/yoga/quickjs) dari dist/<platform>/
    sdl_ver = yoga_ver = qjs_ver = "?"
    if deps_dir:
        info_file = deps_dir / "deps-info.json"
        if info_file.is_file():
            dinfo = json.loads(info_file.read_text())
            sdl_ver = dinfo.get("sdl", {}).get("version", "?")
            yoga_ver = dinfo.get("yoga", {}).get("version", "?")
            qjs_ver = dinfo.get("quickjs", {}).get("version", "?")

        def dep_arc(rel):
            """Petakan path relatif di dist/ -> arcname dalam arsip.

            Library Yoga yang di-cross-compile per ABI tersimpan di
            dist/android/lib/<abi>/, jadi harus masuk ke lib/<abi>/ — bukan
            lib/lib/. File lain (SDL3.so per ABI pun sudah memakai pola
            lib/<abi>/... dari fetch_deps) dipetakan apa adanya."""
            s = str(rel).replace("\\", "/")
            if s.startswith("lib/"):
                return s
            return s

        for p in sorted(deps_dir.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(deps_dir)
            s = str(rel).replace("\\", "/")
            if s.startswith(("include/", "lib/", "bin/", "licenses/")):
                entries.append((dep_arc(s), p))
        # libquickjs.a: build dari amalgam bila mungkin (host build saja)
        qjs_inc = deps_dir / "include" / "quickjs"
        if qjs_inc.is_dir() and system in ("linux", "windows"):
            first_arch = next(iter(skia_outs))
            built = quickjs_static_lib(qjs_inc, deps_dir / "lib", system)
            if built:
                entries.append((f"lib/{first_arch}/{built.name}", built))
                qjs_ver += " (+libquickjs.a)"

    # 4) LICENSE skia + versions.json + README.txt
    lic = skia / "LICENSE"
    if lic.is_file():
        entries.append(("licenses/LICENSE.Skia.txt", lic))

    versions_blob = {
        "skia": {"ref": args.version, "commit": head, "build_type": args.build_type},
        "sdl3": vers["sdl"], "yoga": vers["yoga"], "quickjs": vers["quickjs"],
        "platform": system, "archs": list(skia_outs),
    }

    # Nama arsip: prana-libs-<platform>-<arch>.tar.gz (Android tanpa arch)
    name = bundle_name(system, list(skia_outs))
    target = ROOT / name
    print("> Writing", target)

    first_arch = next(iter(skia_outs))
    readme = README_TMPL.format(version=skia_version, system=system, arch=first_arch,
                                build_type=args.build_type, sdl=sdl_ver,
                                yoga=yoga_ver, qjs=qjs_ver)

    n = 0
    with tarfile.open(target, "w:gz") as tf:
        seen = set()
        for arc, p in entries:
            if arc in seen:
                continue
            seen.add(arc)
            tf.add(str(p), arcname=arc)
            n += 1
        data = json.dumps(versions_blob, indent=2).encode()
        ti = tarfile.TarInfo("versions.json"); ti.size = len(data)
        tf.addfile(ti, io.BytesIO(data)); n += 1
        data = readme.encode()
        ti = tarfile.TarInfo("README.txt"); ti.size = len(data)
        tf.addfile(ti, io.BytesIO(data)); n += 1

    print(f"> {n} files archived -> {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
