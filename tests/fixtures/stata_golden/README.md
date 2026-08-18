# Golden fixture provenance

These fixtures port the do-file corpus of **do2screen (Stata)** — the
behavioural reference for this package — and are used for golden-file
regression and differential (snapshot) tests.

- **Upstream repository**: `randrescastaneda/do2screen` (Stata) — committed at
  `8ac7de8c7e8e33d73c05ac0cca29861312fdc640`.
- **Port scope**: variables tracing mode only (`find`/`range` modes are out of
  scope for do2screen-py).
- **Status**: reconstructed offline at implementation time (no Stata binary was
  available in the build environment). The files are written in the style of
  the upstream corpus; they are **not** byte-copies of upstream files.
  Live exact-line differential verification is tracked as a non-blocking
  follow-up (`DO2SCREEN_STATA_BIN`; see `../../../.cg-docs/plans/2026-08-17-do2screen-py-parser-pipeline.md`
  verification row V13).

No survey microdata or confidential content is contained here or anywhere in
this package.