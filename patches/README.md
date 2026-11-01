# patches/

Patch `.patch` (git-format) diterapkan **non-fatal** ke working tree Skia
oleh `scripts/common/patch.py::apply_all()` setelah checkout:
- patch tidak cocok dengan versi Skia saat ini -> hanya warning, build lanjut
- memakai `git apply` tanpa `--3way` (lesson learned: `--3way` meninggalkan
  file "needs merge" yang merusak incremental rebuild di CI)

Contoh patch historis yang pernah dipakai di repo ini bisa disimpan di sini.
