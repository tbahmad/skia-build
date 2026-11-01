#!/usr/bin/env python3
"""Kemas staging dist/<platform>/ menjadi arsip rilis parana-libs final.

Struktur arsip (prefix parana-libs/):
  include/{skia,SDL3,quickjs,yoga}/
  lib/[<abi>/]<file> + cmake/ParanaLibs/*.cmake
  bin/ (icudtl.dat, SDL3.dll, qjs/qjsc), licenses/, manifest.json, README.md

Nama file arsip:
  linux   -> parana-libs-linux-x86_64-<type>.tar.xz
  windows -> parana-libs-windows-x86_64-<type>.zip
  android -> SATU ZIP PER ABI: parana-libs-android-<abi>-<type>.zip
"""

import argparse, hashlib, json, os, pathlib, shutil, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import archive as arch_mod, util  # noqa: E402
from common.archive import open_archive, archive_name  # noqa: E402
from common.util import DIST_DIR, OUT_DIR, ROOT, log, die  # noqa: E402

from common.archive import display_arch  # x64 -> x86_64 (pola penamaan spesifikasi)


def gen_cmake_module(platform, build_type):
    """Render template CMake/ParanaLibs*.cmake.in dengan placeholder @...@."""
    is_win = platform == "windows"
    if is_win:
        libs = dict(skia="skia.lib", sdl3="SDL3.lib", yoga="yoga.lib", qjs="qjs.lib")
        sys_libs = "opengl32;vulkan-1;d3d11;dxgi;ws2_32;dbghelp;user32;shell32;ole32"
    else:
        libs = dict(skia="libskia.a",
                    sdl3="libSDL3.so" if platform == "android" else "libSDL3.a",
                    yoga="libyoga.a", qjs="libqjs.a")
        sys_libs = ("GLESv2;EGL;log;android;jnigraphics" if platform == "android"
                    else "GL;EGL;vulkan;dl;pthread;m")
    repl = {
        "@SKIA_LIB@": libs["skia"], "@SDL3_LIB@": libs["sdl3"],
        "@YOGA_LIB@": libs["yoga"], "@QJS_LIB@": libs["qjs"],
        "@SYS_LIBS@": sys_libs,
        "@IS_WIN@": "TRUE" if is_win else "FALSE",
        "@IS_ANDROID@": "TRUE" if platform == "android" else "FALSE",
        "@BUILD_TYPE@": build_type,
    }
    tmpl_dir = pathlib.Path(__file__).resolve().parent.parent / "CMake"
    out = {}
    for name in ("ParanaLibsConfig.cmake", "ParanaLibsTargets.cmake"):
        text = (tmpl_dir / (name + ".in")).read_text(encoding="utf-8")
        for k, v in repl.items():
            text = text.replace(k, v)
        out[name] = text
    return out


README_TMPL = """# parana-libs — {platform}/{arch} ({build_type})

Bundle prabuilt **Skia** (+ modul skottie/skparagraph/skshaper/svg),
**SDL3**, **Yoga**, dan **QuickJS** dalam satu arsip, dibangun otomatis oleh
GitHub Actions repo ini (commit Skia `{skia_commit}`; versi lengkap di `manifest.json`).

## Layout
```
include/skia/      header Skia (public + internal + third_party bundled)
include/SDL3/      header SDL3
include/yoga/      header Yoga (#include "yoga/YGNode.h")
include/quickjs/   header + amalgam QuickJS (quickjs.c dst.)
lib/{sub}          library hasil build
cmake/ParanaLibs/  modul CMake (find_package(ParanaLibs))
licenses/          lisensi tiap komponen
bin/               {bin_note}
manifest.json      versi, commit, ukuran & checksum file
```

## Pakai via CMake (disarankan)
```cmake
list(APPEND CMAKE_PREFIX_PATH "<dir-ekstrak>/parana-libs")
find_package(ParanaLibs REQUIRED COMPONENTS skia sdl3 quickjs yoga)
target_link_libraries(app PRIVATE ParanaLibs::skia ParanaLibs::sdl3
                                  ParanaLibs::quickjs ParanaLibs::yoga)
```

## Pakai manual (compile & link)
{link_note}
"""

LINK_NOTES = {
    "linux": """```sh
g++ app.cpp -I<dir>/include/skia -I<dir>/include -L<dir>/lib \\
    -lskia -lskottie -lskparagraph -lskshaper -lsvg \\
    -lSDL3 -lyoga -lqjs -lGL -lEGL -lvulkan -ldl -lpthread -o app
```""",
    "windows": r"""```bat
cl app.cpp /I<dir>\include\skia /I<dir>\include ^
   /link /LIBPATH:<dir>\lib skia.lib skottie.lib skparagraph.lib ^
   skshaper.lib svg.lib SDL3.lib yoga.lib qjs.lib opengl32.lib vulkan-1.lib
```
Salinkan `bin/SDL3.dll` berdekatan dengan `.exe` Anda.""",
    "android": """```sh
$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/clang++ --target=aarch64-linux-android21 \\
    app.cpp -I<dir>/include/skia -I<dir>/include <dir>/lib/<abi>/libskia.a ... \\
    -lGLESv2 -lEGL -llog -landroid -ljnigraphics
```
Atau pakai CMake + NDK toolchain lalu `find_package(ParanaLibs)` (set `PARANA_LIB_ARCH=<abi>`).""",
}


def copy_section(aw, prefix, src_dir, stage, files_map):
    if not src_dir.is_dir():
        return
    for p in sorted(src_dir.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(stage)).replace("\\", "/")
            aw.add(p, prefix + rel)
            files_map[prefix + rel] = p


def make_manifest(platform, arch_label, stage, build_type, files_map):
    bi_path = stage / "build-info.json"
    bi = json.loads(bi_path.read_text()) if bi_path.is_file() else {"components": {}}
    entries = {}
    for arc, src in sorted(files_map.items()):
        p = pathlib.Path(src)
        entries[arc] = {"bytes": p.stat().st_size,
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
    return {
        "package": "parana-libs",
        "version": bi.get("components", {}).get("skia", {}).get("version", ""),
        "generated_by": "scripts/package.py",
        "platform": platform,
        "arch": arch_label,
        "build_type": build_type,
        "components": bi.get("components", {}),
        "files": entries,
    }


def package_stage(platform, arch_label, stage, build_type, fmt=None):
    """Kemas satu staging dir -> satu arsip rilis. Return path arsip."""
    fmt = fmt or ("zip" if platform in ("android", "windows") else "tar.xz")
    fname = archive_name(platform, arch_label, build_type, fmt)
    prefix = "parana-libs/"
    aw = open_archive(OUT_DIR / fname, fmt)

    files_map = {}
    for part in ("include", "lib", "bin", "licenses"):
        copy_section(aw, prefix, stage / part, stage, files_map)

    readme = README_TMPL.format(
        platform=platform, arch=display_arch(arch_label), build_type=build_type,
        skia_commit=util.git_short_head(ROOT / "skia") or "-",
        sub="<abi>/" if platform == "android" else "",
        bin_note=("icudtl.dat, SDL3.dll, qjs.exe, qjsc.exe" if platform == "windows"
                  else "icudtl.dat" + (", libSDL3.so JNI, qjs/qjsc" if platform == "android" else ", qjs, qjsc")),
        link_note=LINK_NOTES[platform])
    aw.add_bytes(prefix + "README.md", readme.encode())

    for fn, content in gen_cmake_module(platform, build_type).items():
        aw.add_bytes(prefix + f"cmake/ParanaLibs/{fn}", content.encode())

    manifest = make_manifest(platform, arch_label, stage, build_type, files_map)
    aw.add_bytes(prefix + "manifest.json", json.dumps(manifest, indent=2).encode())
    aw.close()
    log(f"Paket selesai: {OUT_DIR / fname}")
    return OUT_DIR / fname


def copy_tree_merge(src, dst):
    dst.mkdir(parents=True, exist_ok=True)
    for p in src.rglob("*"):
        if p.is_file():
            out = dst / p.relative_to(src)
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, out)


def filter_buildinfo(bi, abi):
    out = dict(bi)
    comps = {}
    for k, v in bi.get("components", {}).items():
        v = dict(v)
        v["files"] = [f for f in v.get("files", [])
                      if (not f.startswith("lib/")) or f"/{abi}/" in f]
        comps[k] = v
    out["components"] = comps
    out["archs"] = [abi]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", required=True, choices=["linux", "windows", "android"])
    ap.add_argument("--arch", default="x64")
    ap.add_argument("--abis", default="", help="Android; kosong = semua ABI di staging")
    ap.add_argument("--build-type", default=os.environ.get("BUILD_TYPE", "Release"))
    args = ap.parse_args()

    results = []
    if args.platform == "android":
        stage_all = DIST_DIR / "android"
        if not stage_all.is_dir():
            die(f"staging tidak ditemukan: {stage_all}. Jalankan scripts/build.py dulu.")
        abis = [a.strip() for a in args.abis.split(",") if a.strip()]
        if not abis:
            libdir = stage_all / "lib"
            abis = sorted(p.name for p in libdir.iterdir() if p.is_dir()) if libdir.is_dir() else []
        for abi in abis:
            stage = DIST_DIR / f"android-{abi}"
            shutil.rmtree(stage, ignore_errors=True)
            stage.mkdir(parents=True)
            for part in ("include", "licenses", "bin"):
                srcp = stage_all / part
                if srcp.is_dir():
                    copy_tree_merge(srcp, stage / part)
            libsrc = stage_all / "lib" / abi
            if libsrc.is_dir():
                copy_tree_merge(libsrc, stage / "lib")
            bi_f = filter_buildinfo(json.loads((stage_all / "build-info.json").read_text()), abi)
            (stage / "build-info.json").write_text(json.dumps(bi_f, indent=2))
            results.append(package_stage("android", abi, stage, args.build_type))
    else:
        machine = util.canon_arch(args.platform, args.arch)
        stage = DIST_DIR / f"{args.platform}-{machine}"
        if not stage.is_dir():
            die(f"staging tidak ditemukan: {stage}. Jalankan scripts/build.py dulu.")
        results.append(package_stage(args.platform, machine, stage, args.build_type))
    for r in results:
        print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
