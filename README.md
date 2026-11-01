# parana-libs

Pra-build **Skia** (+ modul skottie/skparagraph/skshaper/svg), **SDL3**,
**Yoga**, dan **QuickJS** untuk Linux, Windows, dan Android — dibangun
otomatis lewat GitHub Actions dan dirilis sebagai arsip siap pakai.

## Struktur repo

```
parana-libs/
├── .github/workflows/
│   ├── build-linux.yml          # ubuntu-24.04  -> tar.xz
│   ├── build-windows.yml        # windows-2022  -> zip
│   ├── build-android.yml        # ubuntu (NDK)  -> zip per ABI
│   └── release.yml              # kumpulkan artifact -> GitHub Release
├── config/
│   ├── versions.json            # SATU sumber kebenaran versi dependency
│   ├── platforms.json           # runner, arsitektur, format arsip, ABI->GN cpu
│   └── build-options.json       # GN args & target ninja per platform/build-type
├── scripts/
│   ├── common/                  # download.py extract.py patch.py archive.py util.py
│   ├── dependencies/            # skia.py sdl3.py quickjs.py yoga.py
│   ├── build.py                 # orkestrator: checkout+build semua komponen
│   └── package.py               # kemas staging -> arsip + manifest + cmake module
├── patches/                     # patch Skia non-fatal (lihat patches/README.md)
├── third_party/README.md        # penjelasan sumber dependency (tidak disimpan di git)
├── CMake/                       # template ParanaLibsConfig/Targets.cmake.in
├── README.md
└── LICENSE
```

## Cara build lokal

Prasyarat Linux: `git curl unzip zip xz-utils cmake ninja` + dev libs
(GL/EGL/X11/fontconfig/ALSA dst., lihat workflow). Semua dependency lain
depot_tools, NDK, SDL3, Yoga, QuickJS diunduh otomatis oleh script.

```bash
python3 scripts/build.py   --platform linux --arch x86_64 --build-type Release
python3 scripts/package.py --platform linux --arch x86_64
# hasil: out/parana-libs-linux-x86_64-release.tar.xz
```

Android multi-ABI (satu zip per ABI):

```bash
python3 scripts/build.py   --platform android --abis arm64-v8a,armeabi-v7a
python3 scripts/package.py --platform android
```

## Penamaan arsip output

| Platform | Contoh nama file                                   | Format  |
|----------|----------------------------------------------------|---------|
| linux    | `parana-libs-linux-x86_64-debug.tar.xz`            | tar.xz  |
| windows  | `parana-libs-windows-x86_64-debug.zip`             | zip     |
| android  | `parana-libs-android-arm64-v8a-debug.zip`          | zip     |
| android  | `parana-libs-android-armeabi-v7a-debug.zip`        | zip     |

Pola: `parana-libs-<platform>-<arch/abi>-<buildtype-lower>.<fmt>`

## Struktur isi arsip

```
parana-libs/
├── include/{skia, SDL3, quickjs, yoga}/
├── lib/            # linux: libskia.a libSDL3.a libqjs.a libyoga.a (+ modul skia)
│                   # windows: skia.lib SDL3.lib qjs.lib yoga.lib
│                   # android: <abi>/lib*.so/.a per arsip ABI
├── bin/            # icudtl.dat; windows: SDL3.dll qjs.exe qjsc.exe
├── cmake/ParanaLibs/
│   ├── ParanaLibsConfig.cmake
│   └── ParanaLibsTargets.cmake
├── licenses/       # LICENSE.Skia.txt LICENSE.SDL3.txt LICENSE.yoga.txt ...
├── manifest.json   # versi, commit, ukuran & sha256 tiap file
└── README.md       # petunjuk pemakaian per platform
```

## Pakai dari CMake

```cmake
list(APPEND CMAKE_PREFIX_PATH "<ekstrak>/parana-libs")
find_package(ParanaLibs REQUIRED COMPONENTS skia sdl3 quickjs yoga)
target_link_libraries(app PRIVATE ParanaLibs::skia ParanaLibs::sdl3
                                  ParanaLibs::quickjs ParanaLibs::yoga)
```

## Menaikkan versi dependency

Edit `config/versions.json` lalu push — paths filter pada workflow
(`config/**`, `scripts/**`, `patches/**`) otomatis memicu rebuild ketiga
platform, dan `release.yml` mengumpulkan arsipnya ke GitHub Release.
Alternatif: jalankan workflow manual (`workflow_dispatch`) dengan input
`skia_version` / `build_type`.

Catatan penting warisan pipeline lama yang dipertahankan:
- patch diterapkan **non-fatal** tanpa `git apply --3way`;
- layout header Yoga memakai prefix `include/yoga/` (`#include "yoga/YGNode.h"`);
- nama library canonical: `libqjs.a` (quickjs) dan `libyoga.a` (yogacore);
- QuickJS memakai amalgam resmi agar tidak butuh ICU sistem;
- binari `gn` Windows diambil via CIPD bila depot_tools gagal bootstrap.
