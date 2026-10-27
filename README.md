# Compounding Climate Isolation Across Africa's Road Network

This repository supports the paper **"Compounding climate isolation across
Africa's road network"**. The study examines how climate-driven degradation of
unpaved roads propagates through African road networks, amplifies travel-time
losses, and changes access to healthcare and cities.

## Study overview

African road systems are highly exposed to climate stress because a large share
of the network is unpaved. The paper defines **compounding climate isolation**
as the process by which widespread weather-driven deterioration on unpaved roads
is amplified by network structure and translated into unequal accessibility
losses for people and places with limited routing alternatives.

The analysis combines:

- A continent-scale road network for 49 African countries, including paved and
  unpaved road-surface classification.
- Climate stress indicators from precipitation and soil moisture data.
- Population, health-facility, administrative-boundary, terrain and populated
  place datasets.
- Weighted road-network models that compare normal and extreme-weather travel
  conditions.

## Analytical workflow

The paper uses a coupled workflow:

1. Estimate climate-conditioned speed and passability for unpaved road segments.
2. Build normal and extreme-weather weighted road-network graphs.
3. Measure travel-time change and network-efficiency loss across international,
   national and city-scale networks.
4. Evaluate healthcare accessibility using nearest-facility travel time,
   coverage thresholds and within-country inequality metrics.
5. Identify adaptation bottlenecks by combining climate vulnerability with
   network importance, then test targeted paving scenarios.

## Key findings

- Extreme weather reduces mean road speed by about 10%, but increases travel
  times by 36.3% across connected international city pairs and 41.0% across
  within-country city pairs.
- Network structure amplifies direct road-level degradation by roughly
  3.7-4.5 times.
- Healthcare access losses are unequal: the population share within 1 hour of a
  healthcare facility falls from 88.0% to 81.7% under extreme conditions.
- In 47 of 49 countries, the worst-affected populations experience larger
  travel-time increases than the median group.
- Paving only 0.1% of unpaved roads selected by network importance restores
  71.7% of lost network efficiency, far outperforming random paving.

## Data sources

The study uses publicly available data sources, including:

- Road surface data from Liu et al., available through Figshare:
  <https://doi.org/10.6084/m9.figshare.29424107>
- SRTM terrain data processed through Google Earth Engine.
- CORDEX Africa climate data for precipitation and soil moisture.
- GADM administrative boundaries.
- Natural Earth populated places.
- WorldPop 2020 constrained, UN-adjusted population data.
- OpenStreetMap health-facility locations accessed through the Overpass API.

Large raw datasets are not stored in this repository. Download them from the
original providers and follow their licence terms.

## Repository contents

This checkout contains the analysis code used to reproduce the main paper
results:

- `README.md` - project description and reproduction notes.
- `requirements.txt` - Python dependencies required by the analysis scripts and
  CI checks.
- `data_procession/` - road-layer preparation, climate-conditioned road-speed
  modelling, health-accessibility processing and bottleneck scoring.
- `result1/` - network-scale climate-isolation and amplification analysis.
- `result2/` - healthcare accessibility, inequality, facility-level loss and
  network-buffering analysis.
- `result3/` - bottleneck stability, targeted paving and de-isolation analysis.
- `sensitivity/` - robustness checks and event-based plausibility analyses.
- `tests/` - lightweight CI tests and audit utilities.
- `.github/workflows/ci.yml` - GitHub Actions workflow for Black and pytest.

Large raw datasets and generated intermediate outputs are not tracked in Git.
Most scripts expect a local base directory containing the raw and processed data
folders described in the paper. Where a script exposes command-line arguments,
prefer those over editing paths in source files; otherwise update the `BASE_DIR`
constant at the top of the script before running it.

## Setup

Create a Python environment and install the current dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Run the available checks:

```bash
black --check .
pytest
```

## Licence

Code in this repository is released under the MIT License. Data remain governed
by the licences of their original providers.
