#!/usr/bin/env bash
#
# Copy WASCAL/EC folders from /Volumes/Elements to /Volumes/Extreme SSD/
# excluding all turbulence (high-frequency/raw) data to save space.
#
# Usage: run from terminal (Volumes must be mounted).
#   ./copy_ec_folders_exclude_turbulence.sh           # real copy
#   ./copy_ec_folders_exclude_turbulence.sh --dry-run # show what would be copied
#

# Nicht bei jedem Fehler abbrechen (rsync kann z.B. 23 liefern wenn Ordner während Sync gelöscht wird)
set +e

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

SRC_BASE="/Volumes/Elements"
DST_BASE="/Volumes/Extreme SSD"

# Folders to copy (relative to SRC_BASE)
FOLDERS=(
    "WASCAL_1_GORIGU"
    "WASCAL_5_MOLE"
    "WASCAL_4_JANGA"
    "Janga"
    "Janga_EC"
    "Gorigo"
    "Gorigo EC"
)

# Exclude patterns: turbulence / raw / high-frequency data
# - *.ghg, *.metadata = EddyPro raw (LI-COR)
# - Folders: raw, turbulence, high_frequency, etc.
RSYNC_EXCLUDES=(
    --exclude='*.ghg'
    --exclude='*.metadata'
    --exclude='*turbulence*'
    --exclude='*Turbulence*'
    --exclude='raw/'
    --exclude='raw_data/'
    --exclude='raw_data*/'
    --exclude='high_frequency/'
    --exclude='high_freq/'
    --exclude='hf_data/'
    --exclude='sonic_raw/'
    --exclude='eddy_raw/'
    --exclude='*_raw/'
    --exclude='*_raw_*/'
)
# Optional: exclude raw binary/time series everywhere (uncomment if desired):
# RSYNC_EXCLUDES+=( --exclude='*.bin' --exclude='*.dat' )

echo "Source base: $SRC_BASE"
echo "Destination base: $DST_BASE"
echo "Excluding: turbulence/raw/high-frequency data (*.ghg, *.metadata, raw*, high_freq*, etc.)"
$DRY_RUN && echo "*** DRY RUN – nothing will be written ***"
echo ""

if [[ ! -d "$SRC_BASE" ]]; then
    echo "Error: Source volume not found: $SRC_BASE"
    exit 1
fi
if [[ ! -d "$DST_BASE" ]]; then
    echo "Error: Destination volume not found: $DST_BASE"
    exit 1
fi

mkdir -p "$DST_BASE"

# Build rsync options: -a -v --progress, optional -n for dry-run
RSYNC_OPTS=(-a -v --progress)
$DRY_RUN && RSYNC_OPTS+=(-n)

for folder in "${FOLDERS[@]}"; do
    src="$SRC_BASE/$folder"
    if [[ ! -d "$src" ]]; then
        echo "Skip (not found): $src"
        continue
    fi
    echo "=========================================="
    echo "Copying: $folder"
    echo "  from: $src"
    echo "  to:   $DST_BASE/"
    if rsync "${RSYNC_OPTS[@]}" "${RSYNC_EXCLUDES[@]}" "$src" "$DST_BASE/" 2>&1; then
        echo "  OK: $folder"
    else
        rc=$?
        echo "  WARNING: rsync finished with exit code $rc (script continues with next folder)"
    fi
done

echo ""
echo "Done. Check contents under: $DST_BASE"
