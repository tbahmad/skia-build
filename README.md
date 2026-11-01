# skia-build

Build [Skia](https://skia.org) otomatis via GitHub Actions, terinspirasi dari
[JetBrains/skia-build](https://github.com/JetBrains/skia-build) namun sudah
di-update untuk Skia modern (chrome/m158).

## Workflow yang tersedia

| File | Platform | Trigger |
|---|---|---|
| `.github/workflows/build-skia.yml` | Linux x64 desktop | push ke `main` (jika file terkait berubah) + manual |
| `.github/workflows/build-skia-android.yml` | Android (arm64-v8a, armeabi-v7a, x86_64) | push ke `main` (jika file terkait berubah) + manual |
| `.github/workflows/build-skia-windows.yml` | Windows x64 (MSVC) | push ke `main` (jika file terkait berubah) + manual |
| `.github/workflows/build-bundle.yml` | **Bundle** Linux x64: Skia+SDL3+Yoga+QuickJS | push ke `main` (jika file terkait berubah) + manual |
| `.github/workflows/build-bundle-android.yml` | **Bundle** Android per-ABI | push ke `main` (jika file terkait berubah) + manual |
| `.github/workflows/build-bundle-windows.yml` | **Bundle** Windows x64 (MSVC) | push ke `main` (jika file terkait berubah) + manual |

Ketiga workflow berjalan di runner Linux/Windows — workflow macOS sudah dihapus.

## Cara pakai

### 1. Build manual (paling umum)
1. Buka repo → tab **Actions**.
2. Pilih workflow **"Build Skia"** (Linux), **"Build Skia Android"**, atau **"Build Skia Windows"**.
3. Klik **Run workflow** (tombol biru di kanan atas).
4. Isi parameter:
   - **Versi Skia**: default `chrome/m158`. Bisa juga `main`, `chrome/m150`, atau commit hash.
   - **Tipe build**: `Release` atau `Debug`.
   - *(Android saja)* **ABI**: pilih `arm64-v8a` saja saat uji coba pertama (lebih cepat), atau `arm64-v8a,armeabi-v7a,x86_64` (default).
5. Tunggu sampai selesai (±20–60 menit tergantung ABI & cache).

### 2. Build otomatis
Push perubahan ke branch `main` yang menyentuh file workflow atau `script/**`
akan memicu build otomatis dengan nilai default (`chrome/m158`, Release).

### 3. Ambil hasilnya (artifact)
Setelah run hijau ✅:
1. Buka halaman run tersebut di tab **Actions** (scroll ke bawah).
2. Bagian **Artifacts** → klik nama arsip, misal:
   - `Skia-chrome_m158-linux-Release-x64` (~636 MB)
   - `Skia-chrome_m158-android-Release` (~236 MB)
   - `Skia-chrome_m158-windows-Release-x64`

   > Artifact hanya bertahan 14 hari dan butuh login GitHub untuk mengunduh.
   > Untuk unduhan **publik permanen**, lihat bagian **"Halaman Releases"** di bawah.
3. Ekstrak arsip tar.gz-nya (`tar xzf <file>.tar.gz`). Struktur isinya **rapi siap-pakai development** (binary +
   header yang diperlukan saja — file build seperti `.o` dan test binary tidak ikut):

```
Skia-<versi>-<platform>-<arch>-<tipe>.tar.gz
├── include/skia/               # SEMUA header untuk compile, dalam satu root:
│   ├── include/                #   public headers (core/, codec/, gpu/, ...)
│   ├── modules/                #   skottie, skparagraph, sksg, svg, dst.
│   ├── src/                    #   internal headers (dibutuhkan #include publik)
│   └── third_party/            #   header dependency bundled
├── lib/<arch|abi>/             # library statis: libskia.a, libskottie.a,
│                               # libskparagraph.a, deps bundled (z, png, icu, ...)
├── bin/icudtl.dat              # data ICU (muat saat runtime bila pakai SkUnicode)
├── LICENSE
└── README.txt                  # contoh baris compile/link & integrasi CMake/NDK
```

Dukungan GPU yang ter-compile ke dalam `libskia.a` (semua build):

| Backend | Linux | Android | Windows | Header di arsip |
|---|---|---|---|---|
| OpenGL / GLES | ✅ | ✅ | ✅ (WGL native) | `include/skia/include/gpu/gl/` |
| EGL wrapper | ✅ | ✅ | — | `include/skia/include/gpu/gl/` |
| Vulkan | ✅ | ✅ | ✅ | `include/skia/include/gpu/vk/` |
| Direct3D | — | — | ✅ | `include/skia/include/gpu/d3d/` |

Link tambahan library sistem saat final link aplikasi: Linux `-lGL -lEGL -lvulkan`,
Android NDK `target_link_libraries(app PRIVATE GLESv2 EGL vulkan)`,
Windows `opengl32.lib vulkan-1.lib`. Contoh kode ada di `README.txt` dalam arsip.

Cara pakai singkat:

```bash
# Linux/Android
g++ app.cpp -I$SKIA_DIR/include/skia $SKIA_DIR/lib/x64/lib*.a -lpthread -ldl -o app
```
```bat
:: Windows (MSVC, dari Developer Prompt)
cl app.cpp /I<dir>\include\skia /link /LIBPATH:<dir>\lib\x64 skia.lib skottie.lib ...
```

### 4. Halaman Releases (unduhan publik permanen) ⭐
Workflow **"Build Skia Windows"** punya job `release` yang otomatis membuat /
memperbarui **GitHub Release** setiap build Windows berhasil:

- Tag: `skia-chrome/m158` → halaman: https://github.com/tbahmad/skia-build/releases
- Aset tar.gz dapat diunduh **siapa saja tanpa login**, permanen (tidak terhapus
  seperti artifact), dan punya URL langsung berformat:

  ```
  https://github.com/tbahmad/skia-build/releases/download/<tag>/<nama-file>.tar.gz
  ```

  Contoh (bisa dipakai di CI/CD atau skrip `curl -L -O`):

  ```bash
  curl -L -O https://github.com/tbahmad/skia-build/releases/download/skia-chrome_m158/Skia-chrome_m158-windows-Release-x64.tar.gz
  ```

- Build ulang versi yang sama akan **menimpa aset** pada release yang sama
  (`makeid: false`), jadi tidak ada duplikat file.
- Bila ingin Linux/Android juga masuk ke release yang sama, jalankan dulu
  workflow-nya dalam 14 hari terakhir — pattern unduhan aset pada job `release`
  bisa diperluas ke `Skia-*linux*` / `Skia-*android*`.

## Bundle prana-libs (Skia + SDL3 + Yoga + QuickJS) ⭐

Workflow **Build Bundle** menggabungkan keempat library menjadi satu arsip
berformat **`prana-libs-<platform>-<arch>.tar.gz`**, dipublikasikan ke halaman
Releases dengan tag `prana-libs-<versi-skia>`:

| File rilis | Isi |
|---|---|
| `prana-libs-linux-x64.tar.gz` | Skia + SDL3(static) + libyogacore.a + libquickjs.a + qjs/qjsc |
| `prana-libs-windows-x64.tar.gz` | Skia + SDL3.lib/.dll + yogacore.lib + quickjs.lib + qjs.exe/qjsc.exe |
| `prana-libs-android.tar.gz` | Skia per-ABI + libSDL3.so per-ABI + libyogacore.a per-ABI + amalgam QuickJS |

Struktur di dalam arsip:

```
include/skia/     header Skia (public + internal + third_party bundled)
include/SDL3/     #include <SDL3/SDL.h>
include/yoga/     #include "yoga/YGNode.h"
include/quickjs/  header + amalgam quickjs.c
lib/<arch|abi>/   seluruh library statis/shared tiap komponen
bin/              icudtl.dat, qjs, qjsc, SDL3.dll
licenses/         LICENSE tiap komponen
versions.json     versi pasti tiap komponen
README.txt        contoh perintah compile & link
```

Versi dependency diatur terpusat di `third_party/versions.json`.

## Cara memakai library hasil build

### Android (CMake / NDK)
```cmake
# CMakeLists.txt aplikasi Anda
set(SKIA_ROOT ${CMAKE_SOURCE_DIR}/third_party/skia)   # hasil ekstrak arsip

add_library(skia STATIC IMPORTED)
set_target_properties(skia PROPERTIES
    IMPORTED_LOCATION ${SKIA_ROOT}/libs/${ANDROID_ABI}/libskia.a)

target_include_directories(app PRIVATE
    ${SKIA_ROOT}            # penting: root, bukan hanya include/,
                            # karena ada header yg meng-#include "src/core/Sk*.h"
    ${SKIA_ROOT}/include)

find_library(ANDROID_LIB android log)
target_link_libraries(app PRIVATE skia ${ANDROID_LIB})
```

Contoh kode minimal:
```cpp
#include "include/core/SkCanvas.h"
#include "include/core/SkSurface.h"

sk_sp<SkSurface> surface = SkSurfaces::Raster(SkImageInfo::MakeN32Premul(512, 512));
SkCanvas* canvas = surface->getCanvas();
canvas->clear(SK_ColorWHITE);
```

> Jangan lupa salin `res/<abi>/icudtl.dat` ke aset aplikasi bila memakai
> teks/skottie (inisialisasi ICU dari buffer/file tsb).

### Linux desktop
```bash
g++ app.cpp -I. -std=c++17 \
    third_party/skia/libskia.a \
    -lpthread -ldl -o app
```
(`-I.` mengarah ke root hasil ekstrak agar `#include "src/..."` ikut ketemu.)

### Windows desktop (MSVC)
```bat
cl /EHsc /std:c++17 /I. app.cpp ^
   third_party\skia\skia.lib ^
   opengl32.lib dwmapi.lib gdi32.lib user32.lib advapi32.lib winmm.lib ^
   /link /OUT:app.exe
```
Jalankan dari *Developer Command Prompt for VS* (agar `cl` tersedia). `/I.`
mengarah ke root hasil ekstrak agar `#include "src/..."` ikut ketemu. Library
dibangun dengan RTTI aktif (`extra_cflags_cc=["-frtti"]`) — compile aplikasi
Anda dengan `/GR` (default MSVC).

## Versi & kompatibilitas
- Default: `chrome/m158` (pin versi stabil Chrome).
- Ubah lewat input **Versi Skia** saat Run workflow — tanpa perlu ubah kode.
- Patch JetBrains di `patches/` diterapkan otomatis bila relevan dengan versi terpilih.

## Catatan penting
- **Kuota Actions**: build penuh multi-ABI mahal. Untuk iterasi awal, pilih ABI
  `arm64-v8a` saja. Runner macOS sengaja tidak dipakai (dihitung 10× kuota).
  Runner Windows juga dihitung 2× kuota Linux.
- **Timeout**: tiap job dibatasi 360 menit.
- Artifact disimpan **14 hari**; setelah itu hilang — hasil Windows otomatis
  dipublikasikan ke halaman **Releases** agar permanen & bisa diunduh publik.
- Depot_tools & checkout Skia di-cache per runner untuk mempercepat run berikutnya.

## Struktur repo
```
.github/workflows/
├── build-skia.yml             # Linux desktop (GN + ninja via script/build.py)
├── build-skia-android.yml     # Android multi-ABI (NDK r27c via script/build_android.py)
└── build-skia-windows.yml     # Windows x64 MSVC + job "release" ke GitHub Releases
script/
├── checkout.py                # clone Skia + git-sync-deps (+ bootstrap depot_tools)
├── download_ndk.py            # unduh & ekstrak Android NDK r27c
├── build.py                   # gn gen + ninja (Linux & Windows)
├── build_android.py           # gn gen + ninja per ABI (Android)
├── archive.py                 # kemas tar.gz (Linux & Windows)
└── archive_android.py         # kemas tar.gz per ABI (Android)
patches/                       # patch kompabilitas gaya JetBrains
```
