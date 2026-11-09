#!/bin/bash
# Rebuild every number, table and figure of the paper, then the PDF. CPU only.
# Long steps (run once; their caches are reused): descriptives ~3 min, e6_kernel_norm ~2 min per run set,
# dump_analysis ~15 min per dataset, realmask ~15 min per dataset, baselines ~2 h, o1_o3 ~5 h, e4_downstream ~1-2 h per scenario (needs the
# fold transformers of v16/e4_fold*), batch_check ~3 min. Set QUICK=1 to skip them and only rebuild tables/figures.
set -e
PY=${PY:-/tools/devel/linux/Anaconda/Anaconda3/envs/dmriplayground_latest/bin/python}
cd "$(dirname "$0")"
mkdir -p cache
if [ -z "$QUICK" ]; then
  $PY descriptives.py > cache/descriptives.log 2>&1
  $PY e6_kernel_norm.py > cache/e6_kernel_norm.log 2>&1
  # kernel norms of the v16 runs (when they exist): untouched subjects (E1), HBCD (E3)
  V16=/NIRAL/devel/linux/DTI/testProfiles/ImputeValidation/v16
  for r in E1_s3 E1_s4 E1_s5 E3_s0 E3_s1 E3_s2; do
    [ -f $V16/${r}_report/validation/validation_settings.json ] && \
      $PY e6_kernel_norm.py v16/$r >> cache/e6_kernel_norm.log 2>&1 || true
  done
  $PY dump_analysis.py bcp e1 e3 > cache/dump_analysis.log 2>&1
  $PY realmask.py e1 e3 > cache/realmask.log 2>&1
  $PY batch_check.py > cache/batch_check.log 2>&1
  $PY baselines.py bcp > cache/baselines_bcp.log 2>&1
  $PY o1_o3.py o1 o3 > cache/o1o3.log 2>&1
  for sc in "main --delta 0.3" "d01 --delta 0.1" "d01miss --delta 0.1 --donors missing" \
            "diff03 --delta 0.3 --donors missing --mask-groups g1" "diff01 --delta 0.1 --donors missing --mask-groups g1"; do
    set -- $sc
    tag=$1; shift
    $PY e4_downstream.py --reps 50 --mi 10 --tag $tag "$@" > cache/e4_$tag.log 2>&1
  done
fi
$PY make_tables.py > cache/make_tables.log 2>&1
$PY revision_tables.py > cache/revision_tables.log 2>&1
$PY v16_tables.py > cache/v16_tables.log 2>&1
$PY e4_tables.py > cache/e4_tables.log 2>&1
$PY realmask_tables.py > cache/realmask_tables.log 2>&1
$PY o1o3_tables.py > cache/o1o3_tables.log 2>&1
$PY make_figures.py > cache/make_figures.log 2>&1
cd ..
pdflatex -interaction=nonstopmode main.tex > /dev/null
bibtex main > /dev/null
pdflatex -interaction=nonstopmode main.tex > /dev/null
pdflatex -interaction=nonstopmode main.tex | grep "Output written"
