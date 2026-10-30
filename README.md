# skia-build

Build [Skia](https://skia.org) otomatis via GitHub Actions, terinspirasi dari
[JetBrains/skia-build](https://github.com/JetBrains/skia-build) namun sudah
di-update untuk Skia modern (chrome/m158).

## Workflow yang tersedia

| File | Platform | Trigger |
|---|---|---|
| `.github/workflows/build-skia.yml` | Linux x64 desktop | push ke `main` (jika file terkait berubah) + manual |
| `.github/workflows/build-skia-android.yml` | Android (arm64-v8a, armeabi-v7a, x86_64) | push ke `main` (jika file terkait berubah) + manual |

Keduanya **hanya build untuk Linux runner** — workflow macOS sudah dihapus.

## Cara pakai

### 1. Build manual (paling umum)
1. Buka repo → tab **Actions**.
2. Pilih workflow **"Build Skia"** (Linux) atau **"Build Skia Android"**.
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

## Versi & kompatibilitas
- Default: `chrome/m158` (pin versi stabil Chrome).
- Ubah lewat input **Versi Skia** saat Run workflow — tanpa perlu ubah kode.
- Patch JetBrains di `patches/` diterapkan otomatis bila relevan dengan versi terpilih.

## Catatan penting
- **Kuota Actions**: build penuh multi-ABI mahal. Untuk iterasi awal, pilih ABI
  `arm64-v8a` saja. Runner macOS sengaja tidak dipakai (dihitung 10× kuota).
- **Timeout**: tiap job dibatasi 360 menit.
- Artifact disimpan **14 hari**; setelah itu hilang — unduh dan simpan di release/CDN bila perlu jangka panjang.
- Depot_tools & checkout Skia di-cache per runner untuk mempercepat run berikutnya.

## Struktur repo
```
.github/workflows/
├── build-skia.yml            # Linux desktop (GN + ninja via script/build.py)
└── build-skia-android.yml    # Android multi-ABI (NDK r27c via script/build_android.py)
script/
├── checkout.py               # clone Skia + git-sync-deps (+ bootstrap depot_tools)
├── download_ndk.py           # unduh & ekstrak Android NDK r27c
├── build.py                  # gn gen + ninja (Linux)
├── build_android.py          # gn gen + ninja per ABI (Android)
├── archive.py                # kemas ZIP (Linux)
└── archive_android.py        # kemas ZIP per ABI (Android)
patches/                      # patch kompabilitas gaya JetBrains
```
