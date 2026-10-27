#!/usr/bin/env bash
# Extract only the climate inputs needed for the manuscript and the existing
# 2045/2065/2085 code-window audit. This script does not delete the source ZIP.
set -euo pipefail

archive=${1:?Usage: curate_cordex_archive.sh SOURCE_ZIP DESTINATION_DIR}
destination=${2:?Usage: curate_cordex_archive.sh SOURCE_ZIP DESTINATION_DIR}

files=()
add_pair() {
  local gcm=$1 rcp=$2 dates=$3 variable
  for variable in pr mrso; do
    files+=("${variable}_AFR-44_${gcm}_${rcp}_r1i1p1_SMHI-RCA4_v1_mon_${dates}.nc")
  done
}

# Manuscript baseline, 2011–2020.
add_pair MPI-M-MPI-ESM-LR rcp45 201101-202012

# Manuscript future slices and immediately preceding decades. The latter
# contain the boundary years 2040, 2060 and 2080 selected by current code's
# 2045/2065/2085 ±5-year windows; they are not part of the stated 10-year
# manuscript slices and are retained only until that discrepancy is resolved.
for gcm in MPI-M-MPI-ESM-LR MIROC-MIROC5; do
  for dates in \
    203101-204012 204101-205012 \
    205101-206012 206101-207012 \
    207101-208012 208101-209012; do
    add_pair "$gcm" rcp45 "$dates"
  done
done

# Supplementary Methods S8: MPI RCP8.5 2085, plus the 2080 boundary year.
add_pair MPI-M-MPI-ESM-LR rcp85 207101-208012
add_pair MPI-M-MPI-ESM-LR rcp85 208101-209012

[[ ${#files[@]} -eq 30 ]]
unzip -tq "$archive" >/dev/null
mkdir -p "$destination"

for filename in "${files[@]}"; do
  if [[ -e "$destination/$filename" ]]; then
    printf 'Already exists; refusing overwrite: %s\n' "$destination/$filename" >&2
    exit 1
  fi
  unzip -j -q "$archive" "*/$filename" -d "$destination"
  [[ -s "$destination/$filename" ]]
  printf 'Extracted %s\n' "$filename"
done

printf 'Complete: %s selected NetCDF files in %s\n' "${#files[@]}" "$destination"
