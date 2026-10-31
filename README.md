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
2. Bagian **Artifacts** → klik nama ZIP, misal:
   - `Skia-chrome_m158-linux-Release-x64` (~636 MB)
   - `Skia-chrome_m158-android-Release` (~236 MB)
   - `Skia-chrome_m158-windows-Release-x64`

   > Artifact hanya bertahan 14 hari dan butuh login GitHub untuk mengunduh.
   > Untuk unduhan **publik permanen**, lihat bagian **"Halaman Releases"** di bawah.
3. Ekstrak ZIP-nya. Struktur isinya:

```
Skia-<versi>-<platform>-<tipe>.zip
 Linux: libskia.a dll.| Linux: libskia.a dll.
├── res/<abi>/icudtl.dat        # data ICU (wajib disertakan saat runtime)
├── include/                    # public headers  (include/core/*.h dll.)
├── modules/…                   # header skottie, skparagraph, svg, dll.
├── src/                        # header internal yg di-#include publik header
└── LICENSE
```

### 4. Halaman Releases (unduhan publik permanen) ⭐
Workflow **"Build Skia Windows"** punya job `release` yang otomatis membuat /
memperbarui **GitHub Release** setiap build Windows berhasil:

- Tag: `skia-chrome/m158` → halaman: https://github.com/tbahmad/skia-build/releases
- Aset ZIP dapat diunduh **siapa saja tanpa login**, permanen (tidak terhapus
  seperti artifact), dan punya URL langsung berformat:

  ```
  https://github.com/tbahmad/skia-build/releases/download/<tag>/<nama-file>.zip
  ```

  Contoh (bisa dipakai di CI/CD atau skrip `curl -L -O`):

  ```bash
  curl -L -O https://github.com/tbahmad/skia-build/releases/download/skia-chrome_m158/Skia-chrome_m158-windows-Release-x64.zip
  ```

- Build ulang versi yang sama akan **menimpa aset** pada release yang sama
  (`makeid: false`), jadi tidak ada duplikat file.
- Bila ingin Linux/Android juga masuk ke release yang sama, jalankan dulu
  workflow-nya dalam 14 hari terakhir — pattern unduhan aset pada job `release`
  bisa diperluas ke `Skia-*linux*` / `Skia-*android*`.

## Cara memakai library hasil build

### Android (CMake / NDK)
```cmake
# CMakeLists.txt aplikasi Anda
set(SKIA_ROOT ${CMAKE_SOURCE_DIR}/third_party/skia)   # hasil ekstrak ZIP

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
├── archive.py                 # kemas ZIP (Linux & Windows)
└── archive_android.py         # kemas ZIP per ABI (Android)
patches/                       # patch kompabilitas gaya JetBrains
```
