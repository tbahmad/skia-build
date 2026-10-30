# skia-build

GitHub Actions workflow untuk membangun [Skia](https://skia.org) dari source,
mengadopsi pendekatan [JetBrains/skia-build](https://github.com/JetBrains/skia-build)
(yang sudah diperbarui untuk Skia modern).

## Workflow 1: `.github/workflows/build-skia.yml` (Linux desktop)

Membangun Skia **hanya untuk Linux (ubuntu-24.04)** dengan pipeline:

1. Install dependensi sistem + `depot_tools`
2. `script/checkout.py` → clone Skia + checkout versi yang dipilih + terapkan patch
3. `script/build.py` → konfigurasi `gn gen` (semua dependensi bundled, system libs OFF) + build `ninja`
4. `script/archive.py` → kemas hasil build (`libskia.a`, header, `icudtl.dat`) ke ZIP
5. Upload artifact: `Skia-<versi>-linux-<tipe>-x64.zip`

## Workflow 2: `.github/workflows/build-skia-android.yml` (Android)

File YAML terpisah khusus build Android (ubuntu-24.04 + NDK r27c):

1. `script/checkout.py` → clone Skia (versi default `chrome/m158`)
2. `script/download_ndk.py` → unduh & ekstrak Android NDK r27c (~600 MB)
3. `script/build_android.py` → `gn gen target_os="android"` per ABI (GLES on, Vulkan off, semua dependensi bundled, clang NDK) lalu `ninja`; object file digabung menjadi satu `libskia.a` per ABI via `llvm-ar`
4. `script/archive_android.py` → kemas `libs/<abi>/libskia.a` + header publik ke ZIP
5. Upload artifact: `Skia-<versi>-android-<tipe>.zip`

ABI default: `arm64-v8a, armeabi-v7a, x86_64` (bisa dipilih lewat input `abis`).

## Trigger

- **Run workflow** (manual) dengan input:
  - `skia_version`: `main` | `chrome/mNNN` (mis. `chrome/m158`) | commit hash (default `chrome/m158`)
  - `build_type`: `Release` atau `Debug`
  - `abis` (khusus workflow Android): kombinasi ABI yang diinginkan

## Catatan

- Build Skia cukup berat; runner gratis GitHub Actions mungkin mendekati batas waktu. Pertimbangkan self-hosted runner untuk kecepatan lebih baik.
- Artifact berisi library statis `libskia.a`, header publik Skia, dan data pendukung dalam format ZIP.
