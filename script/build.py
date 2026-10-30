#!/usr/bin/env python3
"""Build Skia dengan gn + ninja (adaptasi script/build.py JetBrains/skia-build, di-update).

GN args mengikuti gaya JetBrains: dependency bundled dari third_party/externals
(system libs dimatikan) -> tidak ada konflik header dengan runner, yang dulu
menyebabkan "4 errors generated" pada partition_alloc/expat/fontconfig.

Perubahan vs versi JetBrains (m93):
  - cxx memakai gcc/g++ default runner (g++-9 sudah tidak tersedia di ubuntu-24.04).
  - is_official_build=false karena clang bawaan depot_tools menolak arg linker
    "-fuse-ld=gold" yang dipaksa oleh official build; ini juga menghindari
    compile error partition_alloc.
  - target 'skia' + modul esensial saja (canvaskit/bentleyottmann dikecualikan).
"""

import argparse, os, pathlib, platform, subprocess, sys


def main():
    os.chdir(os.path.join(os.path.dirname(__file__), os.pardir))
    root = os.getcwd()

    parser = argparse.ArgumentParser()
    parser.add_argument("--build-type", default=os.environ.get("BUILD_TYPE", "Release"),
                        choices=["Release", "Debug"])
    parser.add_argument("--machine", default={"AMD64": "x64", "x86_64": "x64",
                                              "arm64": "arm64"}.get(platform.machine(), "x64"))
    args = parser.parse_args()

    system = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}[platform.system()]
    machine = args.machine
    out = os.path.join(root, "skia", "out", f"{args.build_type}-{machine}")

    gn_args = [
        f'target_cpu="{machine}"',
        # bundled deps (gaya JetBrains) - hindari header sistem runner
        'skia_use_system_expat=false',
        'skia_use_system_libjpeg_turbo=false',
        'skia_use_system_libpng=false',
        'skia_use_system_libwebp=false',
        'skia_use_system_zlib=false',
        'skia_use_system_freetype2=false',
        'skia_use_system_harfbuzz=false',
        'skia_use_system_icu=false',
        'skia_use_sfntly=false',
        'skia_use_freetype=true',
        'skia_use_icu=true',
        'skia_pdf_subset_harfbuzz=true',
        'skia_enable_skottie=true',
        'is_official_build=false',
    ]

    if system == "macos":
        gn_args += [
            'skia_use_metal=true',
            'extra_cflags_cc=["-frtti"]',
        ]
        if machine == "arm64":
            gn_args.append('extra_cflags=["-stdlib=libc++"]')
        else:
            gn_args.append('extra_cflags=["-stdlib=libc++", "-mmacosx-version-min=10.15"]')
    elif system == "linux":
        gn_args += [
            'cc="gcc"',
            'cxx="g++"',
            'extra_cflags_cc=["-frtti"]',
        ]

    skia = os.path.join(root, "skia")
    dt = os.path.join(root, "depot_tools")
    gn = os.path.join(dt, "gn.exe" if system == "windows" else "gn")
    ninja = os.path.join(dt, "ninja.exe" if system == "windows" else "ninja")

    env = os.environ.copy()
    env["PATH"] = dt + os.pathsep + env.get("PATH", "")
    env.setdefault("DEPOT_TOOLS_UPDATE", "0")

    print("> gn gen", out)
    subprocess.check_call([gn, "gen", out, "--args=" + " ".join(gn_args)], env=env, cwd=skia)

    modules = ["modules/skottie", "modules/skparagraph", "modules/skshaper", "modules/svg"]
    targets = ["skia"] + modules
    print("> ninja -C", out, " ".join(targets))
    subprocess.check_call([ninja, "-C", out] + targets, env=env, cwd=skia)

    return 0


if __name__ == "__main__":
    sys.exit(main())
