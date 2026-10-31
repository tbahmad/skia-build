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
        # --- Dukungan GPU (GL) aktif di SEMUA platform ---------------------
        # skia_use_gl=true  : backend OpenGL/GLES klasik via
        #                     include/gpu/gl/ (SkEGLImageBackend.h, dsk, dll.)
        # skia_enable_gpu_debug-tools=true : GrDirectContexts::MakeGL /
        #                     MakeDebugGL tanpa butuh loader EGL sistem.
        # Catatan: skia_use_egl HANYA diaktifkan di platform yang punya header
        # EGL (Linux/Android). Di Windows, egl.h hanya ada di dalam bundle
        # ANGLE sehingga src/gpu/.../GrGLMakeEGLInterface.cpp gagal kompilasi;
        # di sana GL berjalan lewat WGL/native dan Vulkan lewat loader bundled.
        # Backend GPU lain per-platform: Vulkan (linux/android/win),
        # Direct3D+ANGLE (win), Metal (macos) — header gpu/ tetap utuh di ZIP.
        'skia_use_gl=true',
        'skia_enable_gpu_debug-tools=true',
        'skia_enable_gpu=true',
    ]

    # Target OS bisa dioverride (Android: runner Linux tapi target_os="android"
    # via env SKIA_TARGET_OS oleh workflow build-skia-android.yml).
    target_os = os.environ.get("SKIA_TARGET_OS") or system

    if target_os == "android":
        # EGL selalu tersedia di NDK -> aktifkan wrapper EGL + Vulkan.
        gn_args += [
            'skia_use_egl=true',
            'skia_use_vulkan=true',
        ]
    elif system == "macos":
        gn_args += [
            'skia_use_metal=true',
            'extra_cflags_cc=["-frtti"]',
        ]
        if machine == "arm64":
            gn_args.append('extra_cflags=["-stdlib=libc++"]')
        else:
            gn_args.append('extra_cflags=["-stdlib=libc++", "-mmacosx-version-min=10.15"]')
    elif system == "windows":
        # MSVC + ninja dari PATH (vsdevcmd sudah diaktifkan oleh workflow).
        # Skia butuh RTTI untuk consumer C++ -> extra_cflags_cc=["-frtti"].
        # Backend GPU Windows: Direct3D (native) + Vulkan (header & loader dari
        # third_party/vulkan bundled hasil git-sync-deps, tidak butuh SDK).
        # skia_use_egl sengaja TIDAK diaktifkan: header EGL/egl.h di Windows
        # hanya ada dalam bundle ANGLE dan tidak diekspos ke include path,
        # sehingga kompilasi src/gpu/gl/egl gagal (fatal error C1083).
        # GL tetap bisa dipakai via WGL native atau lewat ANGLE/D3D.
        gn_args += [
            'extra_cflags_cc=["-frtti"]',
            'skia_use_direct3d=true',
            'skia_use_vulkan=true',
        ]
    else:  # linux
        gn_args += [
            'cc="gcc"',
            'cxx="g++"',
            'extra_cflags_cc=["-frtti"]',
            # Header EGL/Vulkan tersedia di runner (libegl1-mesa-dev,
            # libvulkan-dev) -> wrapper EGL + backend Vulkan aktif.
            'skia_use_egl=true',
            'skia_use_vulkan=true',
        ]

    skia = os.path.join(root, "skia")
    dt = os.path.join(root, "depot_tools")
    ext = ".exe" if system == "windows" else ""

    def find_tool(name):
        """Cari binari gn/ninja asli, hindari wrapper depot_tools yang butuh
        bootstrap (python3_bin_reldir.txt)."""
        import glob as _glob
        from shutil import which

        def usable(p):
            if not p or os.path.isdir(p):
                return False
            # Di Windows, script .bat/.ps1 depot_tools tidak bisa dieksekusi
            # via CreateProcess langsung -> hanya terima .exe.
            if system == "windows":
                return p.lower().endswith(".exe") and os.path.isfile(p)
            return os.access(p, os.X_OK)

        # 0) binari di PATH sistem (Windows: ninja.exe dari runner; gn bila ada)
        w = which(name)
        if usable(w):
            return w
        # 1) hasil unduhan git-sync-deps: third_party/<name>/<os>*/<name>[.exe]
        for cand in sorted(_glob.glob(os.path.join(skia, "third_party", name, "*", name + ext))):
            if usable(cand):
                return cand
        # 2) binari CIPD di cache depot_tools
        for cand in sorted(_glob.glob(os.path.join(dt, ".cipd", "**", name + ext), recursive=True)):
            if usable(cand):
                return cand
        # 3) hasil prefetch / unduhan CIPD checkout.py di folder depot_tools
        cand = os.path.join(dt, name + ext)
        if usable(cand):
            return cand
        cipd_bin = os.path.join(dt, "cipd-bin", name + ext)
        if usable(cipd_bin):
            return cipd_bin
        # 4) terakhir: wrapper depot_tools (mungkin memicu bootstrap saat dipanggil)
        return cand

    gn = find_tool("gn")
    ninja = find_tool("ninja")
    print("> menggunakan gn   :", gn)
    print("> menggunakan ninja:", ninja)

    env = os.environ.copy()
    env["PATH"] = dt + os.pathsep + env.get("PATH", "")
    env.setdefault("DEPOT_TOOLS_UPDATE", "0")

    print("> gn gen", out)
    print(">   args:", " ".join(gn_args))
    rc = subprocess.call([gn, "gen", out, "--args=" + " ".join(gn_args)], env=env, cwd=skia)
    if rc != 0:
        # cetak isi args.gn & daftar tool yang tersedia untuk diagnosis
        ag = os.path.join(out, "args.gn")
        if os.path.exists(ag):
            print("----- args.gn -----")
            print(open(ag).read())
        sys.exit(f"ERROR: 'gn gen' gagal (exit {rc}). Lihat pesan di atas.")

    modules = ["modules/skottie", "modules/skparagraph", "modules/skshaper", "modules/svg"]
    targets = ["skia"] + modules
    print("> ninja -C", out, " ".join(targets))
    subprocess.check_call([ninja, "-C", out] + targets, env=env, cwd=skia)

    return 0


if __name__ == "__main__":
    sys.exit(main())
