#!/usr/bin/env python3
"""Orkestrator build parana-libs: Skia + SDL3 + Yoga + QuickJS untuk satu platform.

Pemakaian (dipanggil workflow CI atau manual):
  python3 scripts/build.py --platform linux   --arch x86_64 --build-type Release
  python3 scripts/build.py --platform windows --arch x86_64 --build-type Debug
  python3 scripts/build.py --platform android --abis arm64-v8a,armeabi-v7a

Alur:
  1. dependencies/skia.py      checkout + build (gn/ninja; multi-ABI utk android)
  2. dependencies/{sdl3,yoga,quickjs}.py  prepare() -> staging dist/<plat>/...
  3. hasil staging dinormalisasi ke nama canonical parana-libs + build-info.json

Hasil akhir per platform ada di dist/<platform>[-<arch>]/ dengan layout:
  include/{skia,SDL3,quickjs,yoga}/  lib/[<abi>/]  bin/  licenses/  build-info.json
"""

import argparse, json, os, pathlib, shutil, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import util  # noqa: E402
from common.util import ROOT, DIST_DIR, log, warn, die, load_config  # noqa: E402
from dependencies import skia as skia_mod, sdl3 as sdl3_mod, \
    yoga as yoga_mod, quickjs as quickjs_mod  # noqa: E402


def download_ndk(dest=None):
    """Unduh Android NDK (dipakai saat platform=android). Return path NDK."""
    import io, zipfile
    from common.download import download
    ver = load_config("versions")["android_ndk"]["version"]
    dest = pathlib.Path(dest or ROOT / "android-ndk")
    if (dest / "source.properties").is_file():
        log("NDK sudah ada:", dest)
        return dest
    url = (f"https://dl.google.com/android/repository/"
           f"android-ndk-r{ver.split('.')[0]}{''}-linux.zip")
    # pakai penamaan resmi: rXX -> folder; simpan seperti pipeline lama
    url = f"https://dl.google.com/android/repository/android-ndk-r{int(float(ver.split('.',1)[0]))}-linux.zip" \
        if False else url
    zipdst = ROOT / "ndk.zip"
    download(url, zipdst)
    log("Mengekstrak NDK ... (± 1 GB)")
    with zipfile.ZipFile(zipdst) as zf:
        names = [n for n in zf.namelist() if "/" in n]
        top = names[0].split("/")[0]
        for m in zf.infolist():
            if m.is_dir():
                continue
            rel = m.filename.split("/", 1)[1] if m.filename.startswith(top + "/") else None
            if rel is None:
                continue
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(m) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    zipdst.unlink(missing_ok=True)
    (dest / "source.properties").write_text(f"Pkg.Revision = {ver}\n")
    return dest


def stage_skia(platform, arch_label, out_dir, stage, build_type):
    """Salin hasil build skia out/<type>-<label> ke staging layout parana-libs."""
    inc = stage / "include" / "skia"
    headers = skia_mod.collect_headers()
    for rel, p in headers:
        dst = inc / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            shutil.copy2(p, dst)
    suffix = ".lib" if platform == "windows" else ".a"
    libdst = stage / "lib" if platform != "android" else stage / "lib" / arch_label
    libdst.mkdir(parents=True, exist_ok=True)
    libs = skia_mod.find_libs(out_dir, suffix)
    names = []
    for p in libs:
        shutil.copy2(p, libdst / p.name)
        names.append(f"lib/{p.name}" if platform != "android" else f"lib/{arch_label}/{p.name}")
    icu = pathlib.Path(out_dir) / "icudtl.dat"
    bins = []
    if icu.is_file():
        (stage / "bin").mkdir(exist_ok=True)
        shutil.copy2(icu, stage / "bin" / "icudtl.dat")
        bins.append("bin/icudtl.dat")
    lic = skia_mod.SKIA_DIR / "LICENSE"
    if lic.is_file():
        (stage / "licenses").mkdir(exist_ok=True)
        shutil.copy2(lic, stage / "licenses" / "LICENSE.Skia.txt")
    return {"component": "skia", "version": os.environ.get("SKIA_VERSION", "main"),
            "commit": util.git_short_head(skia_mod.SKIA_DIR),
            "build_type": build_type, "files": names + bins,
            "header_count": len(headers)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", default=None,
                    help="linux|windows|android (default: host)")
    ap.add_argument("--arch", default=None, help="x86_64|x64 (default: host / config)")
    ap.add_argument("--abis", default=None, help="Android: daftar ABI pisah koma")
    ap.add_argument("--build-type", default=os.environ.get("BUILD_TYPE", "Release"),
                    choices=["Release", "Debug"])
    ap.add_argument("--skip-skia-build", action="store_true",
                    help="pakai out/ skia yang sudah ada (untuk CI bertahap)")
    args = ap.parse_args()

    platforms = load_config("platforms")
    platform = args.platform or ("android" if os.environ.get("SKIA_TARGET_OS") == "android"
                                 else util.host_system())
    if platform not in platforms:
        die(f"platform tidak dikenal: {platform} (pilihan: {', '.join(platforms)})")
    plat_cfg = platforms[platform]

    if platform == "android":
        abis = [a.strip() for a in (args.abis or os.environ.get("ANDROID_ABIS")
                                    or ",".join(plat_cfg["archs"])).split(",") if a.strip()]
        arches = abis
        machine = "x64"
    else:
        machine = util.canon_arch(platform, args.arch or os.environ.get("ARCH") or "x64")
        arches = [machine]

    stage_name = f"{platform}" if platform == "android" else f"{platform}-{machine}"
    stage = DIST_DIR / stage_name
    if stage.exists():
        shutil.rmtree(stage)
    (stage / "include").mkdir(parents=True)

    build_info = {"package": "parana-libs", "platform": platform,
                  "archs": arches, "build_type": args.build_type,
                  "components": {}}

    # --- 1. Skia -------------------------------------------------------------
    if not args.skip_skia_build:
        skia_mod.checkout(os.environ.get("SKIA_VERSION"))
    ndk = None
    if platform == "android":
        ndk = os.environ.get("ANDROID_NDK_ROOT") or str(download_ndk())
        os.environ["ANDROID_NDK_ROOT"] = ndk
    outs = {}
    if not args.skip_skia_build:
        outs = skia_mod.build(platform, machine, args.build_type, abis if platform == "android" else None, ndk)
    else:
        for label in arches:
            od = skia_mod.SKIA_DIR / "out" / f"{args.build_type}-{label}"
            if od.is_dir():
                outs[label] = od
    if not outs:
        die("direktori out Skia tidak ditemukan; jalankan build tanpa --skip-skia-build")
    for label, od in outs.items():
        info = stage_skia(platform, label, od, stage, args.build_type)
        if platform == "android":
            build_info["components"].setdefault("skia", {"version": info["version"],
                                                          "commit": info["commit"],
                                                          "build_type": args.build_type,
                                                          "files": [], "header_count": info["header_count"]})
            build_info["components"]["skia"]["files"] += info["files"]
        else:
            build_info["components"]["skia"] = info

    # --- 2. SDL3 --------------------------------------------------------------
    try:
        r = sdl3_mod.prepare(platform, machine, stage)
        if platform == "android":
            keep = set(build_info["components"].get("sdl3", {}).get("files", []))
            r["files"] = [f for f in r["files"] if any(f.endswith(a) or f"/{a}/" in f
                                                       for a in arches)] or r["files"]
        build_info["components"]["sdl3"] = r
    except SystemExit:
        raise
    except Exception as e:
        die(f"persiapan SDL3 gagal: {e}")

    # --- 3. Yoga --------------------------------------------------------------
    r = yoga_mod.prepare(platform, machine, stage,
                         abis=arches if platform == "android" else None, ndk=ndk)
    if platform == "android":
        r["files"] = [f for f in r["files"] if f.split("/")[1] in arches]
    build_info["components"]["yoga"] = r

    # --- 4. QuickJS -----------------------------------------------------------
    r = quickjs_mod.prepare(platform, machine, stage, machine=machine)
    build_info["components"]["quickjs"] = r

    # --- normalisasi nama library canonical (libquickjs.a -> libqjs.a dst.) --
    # (dependency module sudah menulis nama canonical; skia modul tetap asli)

    (stage / "build-info.json").write_text(json.dumps(build_info, indent=2))
    log("Build staging selesai ->", stage)
    print(json.dumps(build_info, indent=2)[:2000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
