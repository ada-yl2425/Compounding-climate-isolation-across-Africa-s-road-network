#!/bin/bash

BASE="path/to/your/base/directory"
ROADS="$BASE/RAW/Road_data"
SPEED="$BASE/road_speed_cordex"
NODES="$BASE/web/country_layer"

COUNTRIES=(
    Algeria Angola Benin Botswana BurkinaFaso Burundi Cameroon
    CentralAfrican Chad Congo CongoDR Djibouti Egypt Equatorial
    Eritrea Ethiopia Gabon Gambia Ghana Guinea GuineaBissau
    IvoryCoast Kenya Lesotho Liberia Libya Madagascar Malawi
    Mali Mauritania Morocco Mozambique Namibia Niger Nigeria
    Rwanda Senegal SierraLeone Somalia SouthAfrica SouthSudan
    Sudan Swaziland Tanzania Togo Tunisia Uganda WestSahara
    Zambia Zimbabwe
)

DONE=0
SKIP=0
FAIL=0

for COUNTRY in "${COUNTRIES[@]}"; do
    SHP="$ROADS/$COUNTRY/$COUNTRY.shp"
    IRI="$SPEED/${COUNTRY}_road_speed.csv"
    CITY_NODES="$NODES/${COUNTRY}_city_nodes.csv"

    if [ ! -f "$SHP" ]; then
        echo "[SKIP] $COUNTRY - Shapefile missing"
        SKIP=$((SKIP + 1))
        continue
    fi
    if [ ! -f "$IRI" ]; then
        echo "[SKIP] $COUNTRY - Speed CSV missing"
        SKIP=$((SKIP + 1))
        continue
    fi
    if [ ! -f "$CITY_NODES" ]; then
        echo "[SKIP] $COUNTRY - city_nodes CSV missing"
        SKIP=$((SKIP + 1))
        continue
    fi

    echo ""
    echo "========================================================"
    echo "  Running: $COUNTRY"
    echo "========================================================"

    python web/network_pipeline.py \
        --layer country \
        --country "$COUNTRY" \
        --surface "" \
        --shp "$SHP" \
        --iri "$IRI" \
        --nodes "$CITY_NODES"

    if [ $? -eq 0 ]; then
        DONE=$((DONE + 1))
    else
        echo "[ERROR] $COUNTRY execution failed"
        FAIL=$((FAIL + 1))
    fi
done

echo ""
echo "========================================================"
echo "  All Complete: Success=$DONE  Skipped=$SKIP  Failed=$FAIL"
echo "========================================================"
