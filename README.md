# skia-build

GitHub Actions workflow untuk membangun [Skia](https://skia.org) dari source,
mengadopsi pendekatan [JetBrains/skia-build](https://github.com/JetBrains/skia-build)
(yang sudah diperbarui untuk Skia modern).

## Workflow: `.github/workflows/build-skia.yml`

Membangun Skia **hanya untuk Linux (ubuntu-24.04)** dengan pipeline:

1. Install dependensi sistem + `depot_tools`
2. `script/checkout.py` → clone Skia + checkout versi yang dipilih + terapkan patch
3. `script/build.py` → konfigurasi `gn gen` (semua dependensi bundled, system libs OFF) + build `ninja`
4. `script/archive.py` → kemas hasil build (`libskia.a`, header, `icudtl.dat`) ke ZIP
5. Upload artifact: `Skia-<versi>-linux-<tipe>-x64.zip`

## Trigger

- **Run workflow** (manual) dengan input:
  - `skia_version`: `main` | `chrome/mNNN` (mis. `chrome/m148`) | commit hash (default `chrome/m148`)
  - `build_type`: `Release` atau `Debug`

## Catatan

- Build Skia cukup berat; runner gratis GitHub Actions mungkin mendekati batas waktu. Pertimbangkan self-hosted runner untuk kecepatan lebih baik.
- Artifact berisi library statis `libskia.a`, header publik Skia, dan data pendukung dalam format ZIP.
