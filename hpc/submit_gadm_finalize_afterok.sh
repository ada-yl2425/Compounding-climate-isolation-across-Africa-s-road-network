#!/usr/bin/env bash
# Submit the finalizer only after the 49-country array has succeeded.
set -euo pipefail

if test "$#" -ne 1 || ! [[ "$1" =~ ^[0-9]+\[\](\.[A-Za-z0-9._-]+)?$ ]]; then
  echo "usage: $0 <PBS_ARRAY_JOB_ID> (e.g. 12345[].pbs-7)" >&2
  exit 2
fi
array_job_id="$1"
: "${GADM_CODE_ROOT:?}"
: "${GADM_SOURCE:?}"
: "${GADM_REGISTRY:?}"
: "${GADM_MANIFEST:?}"
: "${GADM_OUTPUT_ROOT:?}"
: "${GADM_FINAL_MANIFEST:?}"
: "${GADM_FINAL_CSV:?}"
: "${GADM_PYTHON:?}"

for value in "$GADM_CODE_ROOT" "$GADM_SOURCE" "$GADM_REGISTRY" "$GADM_MANIFEST" \
             "$GADM_OUTPUT_ROOT" "$GADM_FINAL_MANIFEST" "$GADM_FINAL_CSV" "$GADM_PYTHON"; do
  if [[ "$value" == *","* || "$value" == *$'\n'* ]]; then
    echo "qsub -v values cannot contain commas or newlines" >&2
    exit 2
  fi
done

script="$GADM_CODE_ROOT/hpc/pbs_gadm_admin_finalize.pbs"
test -f "$script"
qsub -W "depend=afterok:$array_job_id" \
  -v "GADM_CODE_ROOT=$GADM_CODE_ROOT,GADM_SOURCE=$GADM_SOURCE,GADM_REGISTRY=$GADM_REGISTRY,GADM_MANIFEST=$GADM_MANIFEST,GADM_OUTPUT_ROOT=$GADM_OUTPUT_ROOT,GADM_FINAL_MANIFEST=$GADM_FINAL_MANIFEST,GADM_FINAL_CSV=$GADM_FINAL_CSV,GADM_PYTHON=$GADM_PYTHON" \
  "$script"
