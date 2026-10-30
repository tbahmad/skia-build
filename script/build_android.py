#!/usr/bin/env python3
"""Build Skia untuk Android dengan gn + ninja (gaya JetBrains/skia-build, di-update).

Kebutuhan toolchain:
  - NDK Android r27+ (diunduh otomatis via download_ndk.py bila belum ada),
    diarahkan lewat env ANDROID_NDK_ROOT.
  - depot_tools sudah di-bootstrap (checkout.py) -> gn/ninja tersedia.

Strategi GN args (menghindari error yang pernah terjadi di build Linux):
  - Semua dependency DI-BUNDLE dari third_party/externals
    (system libs OFF) -> tidak ada konflik header dengan runner.
  - skia_use_gl=true memakai backend OpenGL ES (OpenGL desktop & Vulkan
    dimatikan karena tidak tersedia di Android).
  - is_official_build=false -> hindari arg linker "-fuse-ld=gold" dan
    masalah partition_alloc.
  - cc/cxx memakai clang bawaan NDK (satu-satunya compiler yang valid
    untuk target Android).

Menghasilkan satu library statis gabungan per ABI: out/<type>-<abi>/obj/libskia.a
"""

import argparse, os, pathlib, platform, subprocess, sys

DEFAULT_ABIS = ["arm64-v8a", "armeabi-v7a", "x86_64"]


def find_tool(root, name):
    """Cari binari gn/ninja asli (hindari wrapper depot_tools yang butuh bootstrap)."""
    import glob as _glob
    from shutil import which
    skia = os.path.join(root, "skia")
    dt = os.path.join(root, "depot_tools")
    # 1) hasil unduhan git-sync-deps: third_party/<name>/linux*/<name>
    for cand in sorted(_glob.glob(os.path.join(skia, "third_party", name, "*", name))):
        if os.access(cand, os.X_OK) and not os.path.isdir(cand):
            return cand
    # 2) binari CIPD di cache depot_tools
    exe = name + (".exe" if platform.system() == "Windows" else "")
    for cand in sorted(_glob.glob(os.path.join(dt, ".cipd", "**", exe), recursive=True)):
        if os.access(cand, os.X_OK) and not os.path.isdir(cand):
            return cand
    # 3) PATH sistem
    w = which(name)
    if w:
        return w
    # 4) terakhir: wrapper depot_tools
    return os.path.join(dt, exe)


def main():
    os.chdir(os.path.join(os.path.dirname(__file__), os.pardir))
    root = os.getcwd()
    skia = os.path.join(root, "skia")

    parser = argparse.ArgumentParser()
    parser.add_argument("--build-type", default=os.environ.get("BUILD_TYPE", "Release"),
                        choices=["Release", "Debug"])
    parser.add_argument("--abis", default=os.environ.get("ANDROID_ABIS", ",".join(DEFAULT_ABIS)),
                        help="Daftar ABI yang dipisah koma (default: arm64-v8a,armeabi-v7a,x86_64)")
    args = parser.parse_args()
    abis = [a.strip() for a in args.abis.split(",") if a.strip()]

    # --- NDK ---------------------------------------------------------------
    ndk = os.environ.get("ANDROID_NDK_ROOT") or os.environ.get("NDK_ROOT") \
        or os.environ.get("ANDROID_NDK_HOME")
    if not ndk or not os.path.isdir(ndk):
        print("> ANDROID_NDK_ROOT tidak diset; mencoba unduh NDK ...")
        rc = subprocess.call([sys.executable, os.path.join(root, "script", "download_ndk.py")])
        if rc != 0:
            sys.exit("ERROR: gagal menyiapkan Android NDK")
        ndk = os.path.join(root, "android-ndk")
    ndk = os.path.abspath(ndk)
    print("> Menggunakan NDK:", ndk)

    # llvm-ar dari NDK (untuk menggabungkan .o menjadi libskia.a gabungan)
    prebuilt = pathlib.Path(ndk, "toolchains", "llvm", "prebuilt")
    host_dirs = sorted(p for p in prebuilt.glob("*") if (p / "bin").is_dir()) \
        if prebuilt.is_dir() else []
    toolchain_bin = str(host_dirs[0] / "bin") if host_dirs \
        else str(prebuilt / "linux-x86_64" / "bin")

    gn = find_tool(root, "gn")
    ninja = find_tool(root, "ninja")
    print("> menggunakan gn   :", gn)
    print("> menggunakan ninja:", ninja)

    env = os.environ.copy()
    env["PATH"] = os.path.join(root, "depot_tools") + os.pathsep + env.get("PATH", "")
    env.setdefault("DEPOT_TOOLS_UPDATE", "0")
    env["ANDROID_NDK_ROOT"] = ndk
    env["NDK_ROOT"] = ndk

    failed = []
    for abi in abis:
        out = os.path.join(skia, "out", f"{args.build_type}-{abi}")
        gn_args = [
            'target_os="android"',
            f'target_cpu="{abi}"',
            f'android_ndk_path="{ndk}"',
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
            # grafis: GLES saja (Vulkan & OpenGL desktop tidak ada di Android)
            'skia_use_gl=true',
            'skia_use_vulkan=false',
            'skia_enable_gpu=true',
            # toolchain NDK
            'cc="clang"',
            'cxx="clang++"',
            'extra_cflags_cc=["-frtti"]',
            'is_official_build=false',
        ]
        if args.build_type == "Release":
            gn_args += ['is_debug=false', 'is_component_build=false']
        else:
            gn_args.append('is_debug=true')

        print(f"\n===== [{abi}] gn gen {out} =====")
        print(">   args:", " ".join(gn_args))
        rc = subprocess.call([gn, "gen", out, "--args=" + " ".join(gn_args)], env=env, cwd=skia)
        if rc != 0:
            ag = os.path.join(out, "args.gn")
            if os.path.exists(ag):
                print("----- args.gn -----")
                print(open(ag).read())
            print(f"ERROR: gn gen gagal untuk {abi} (exit {rc})")
            failed.append(abi)
            continue

        targets = ["skia", "modules/skottie", "modules/skparagraph",
                   "modules/skshaper", "modules/svg"]
        print(f"===== [{abi}] ninja -C {out} {' '.join(targets)} =====")
        rc = subprocess.call([ninja, "-C", out] + targets, env=env, cwd=skia)
        if rc != 0:
            print(f"ERROR: ninja gagal untuk {abi} (exit {rc})")
            failed.append(abi)
            continue

        # gabungkan semua .o menjadi satu libskia.a gabungan (gaya JetBrains)
        obj_dir = os.path.join(out, "obj")
        combined = os.path.join(obj_dir, "libskia.a")
        ar = os.path.join(toolchain_bin, "llvm-ar")
        if not os.path.exists(ar):
            ar = "ar"
        objs = sorted(str(p) for p in pathlib.Path(obj_dir).rglob("*.o"))
        if objs:
            print(f"> Menggabungkan {len(objs)} object file -> {combined}")
            rsp = os.path.join(out, "libskia.rsp")
            with open(rsp, "w") as f:
                f.write(" ".join(objs))
            # gunakan script mode agar tidak kena batas panjang argumen
            mri = os.path.join(out, "libskia.mri")
            with open(mri, "w") as f:
                f.write("CREATE %s\n" % combined)
                for o in objs:
                    f.write("ADDLIB %s\n" % o)
                f.write("SAVE\nEND\n")
            r = subprocess.run([ar, "-MRI", mri], env=env, capture_output=True, text=True)
            if r.returncode != 0:
                print("WARNING: penggabungan libskia.a gagal:", r.stderr[:500])
        print(f"> Selesai {abi}: {combined}")

    if failed:
        sys.exit(f"ERROR: build gagal untuk ABI: {', '.join(failed)}")
    print("\n> Semua ABI berhasil dibangun:", ", ".join(abis))
    return 0


if __name__ == "__main__":
    sys.exit(main())
