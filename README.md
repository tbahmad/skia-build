# skia-build

GitHub Actions workflow untuk membangun [Skia](https://skia.org) dari source.

## Workflow: `.github/workflows/build-skia.yml`

Membangun Skia untuk **Linux (ubuntu-22.04)** dan **macOS (macos-13)** dengan pipeline standar:

1. Install dependensi sistem + `depot_tools` (dengan cache paket cipd)
2. `fetch skia` → checkout ref yang dipilih → `git-sync-deps`
3. Konfigurasi dengan `gn gen` (clang, GL/Vulkan di Linux, Metal/GL di macOS)
4. Build dengan `ninja`
5. Smoke test `dm` (non-fatal)
6. Upload artifact hasil build (`skia-linux-<mode>.tar.gz`, `skia-macos-<mode>.tar.gz`)

## Trigger

- **Push / Pull Request** ke branch `main` → build otomatis mode `release`.
- **Run workflow** (manual) dengan input:
  - `skia_ref`: branch/tag/commit Skia (default `chrome/m120`)
  - `build_mode`: `release` atau `debug`

## Catatan

- Build Skia cukup berat; runner gratis GitHub Actions mungkin mendekati batas waktu. Pertimbangkan self-hosted runner untuk kecepatan lebih baik.
- Artifact berisi seluruh direktori `out/<mode>` tanpa file objek, termasuk library statis (`libskia.a`), shared libs, dan tool seperti `dm`, `gm`, `nanobench`.
