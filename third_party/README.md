# third_party

Direktori ini adalah **tempat kerja (working area)** untuk sumber dependency
yang diunduh otomatis oleh `scripts/` — isinya TIDAK disimpan di git.

| Folder            | Diisi oleh                    | Sumber |
|-------------------|-------------------------------|--------|
| `skia/`           | `scripts/dependencies/skia.py`| https://skia.googlesource.com/skia.git |
| `SDL/`            | `scripts/dependencies/sdl3.py`| https://github.com/libsdl-org/SDL (tag SDL3) |
| `quickjs/`        | `scripts/dependencies/quickjs.py` | https://github.com/QuickJS/QuickJS (Bellard) |
| `yoga/`           | `scripts/dependencies/yoga.py`| https://github.com/facebook/yoga |
| `depot_tools/`    | `scripts/common/download.py`  | https://chromium.googlesource.com/chromium/tools/depot_tools.git |
| `android-ndk*/`   | `scripts/build.py::download_ndk` | https://dl.google.com/android/repository (versi dari config/versions.json) |

Versi tiap komponen diatur terpusat di **`config/versions.json`**.
Hasil build dikemas ke `dist/<platform>-<arch>/` lalu menjadi arsip
`out/parana-libs-<platform>-<arch>-<tipe>.tar.xz|.zip` oleh `scripts/package.py`.

Jangan commit isi direktori ini; hapus kapan saja bila butuh ruang disk —
script akan mengunduh ulang sesuai konfigurasi.
