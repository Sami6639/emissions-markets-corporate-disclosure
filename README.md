# Emissions Markets and Corporate Environmental Disclosure: A Cross-Country Analysis

Replication code, public-source inputs, numerical results and figures for the manuscript by **Sami Küçükoğlu**. Release **v1.0.0**, 13 November 2026.

## Evidence covered

| Component | Sample | Main outcome |
|---|---|---|
| India | 318 eligible plants; randomized original assignment | Availability of regulatory emissions estimates and monitoring coverage |
| China | 80 firms, 480 firm-years, 13 provinces | Annual-report carbon-market content during national-market implementation |
| International context | 1,659 firms across 50 jurisdictions | Aggregate coverage of reported carbon fields in the supplied LSEG archive |

The public-data analyses reproduce a **22.5 percentage-point** Indian monthly-availability effect, a **24.4-point** calibrated monitoring-coverage effect and a **60.8-point** adjusted Chinese reporting contrast. The research designs, policy-timing qualifications and sensitivity results are documented in [Methods and validation](docs/METHODS_AND_VALIDATION.md). The international analysis has a separate descriptive and contextual role.

## Reproduce

Use Python 3.12. From the repository root:

```bash
python -m venv .venv
# Activate the environment using the command appropriate to your operating system.
python -m pip install -r requirements.txt
python verify_integrity.py
python prepare_inputs.py
python reproduce.py
```

`prepare_inputs.py` retrieves seven large public data files directly from Harvard Dataverse and Mendeley Data and verifies their SHA-256 hashes. It requires network access once (about 117 MB); already verified files are reused. Smaller public inputs are included in the repository.

`reproduce.py` then runs the Indian and Chinese numerical pipelines offline in dependency order, including selection bounds, measurement reconstruction, bootstrap inference, overlap weighting, small-cluster checks, policy-timing checks, semantic-audit summaries and exact binary-outcome classification sensitivity. It stops on the first failure and writes diagnostic output to `run_logs/`. These steps require no LSEG subscription or company-report downloads. Bootstrap calculations can take several minutes. The original 12-step pipeline and the added classification-sensitivity step have each been executed and verified.

To inspect the archived results or rebuild figures without repeating all estimations:

```bash
python verify_results.py
python reproduce.py --figures-only
```

The four main figures are in [`figures/`](figures/). Machine-readable values and notes for the five main tables are in [`docs/MAIN_TABLE_VALUES.json`](docs/MAIN_TABLE_VALUES.json). Full numerical outputs are retained under each analysis's `results/` directory.

## Contents

- [`manuscript_20261113/`](manuscript_20261113/): Indian experimental reanalysis, public replication inputs and measurement audit. The folder name is retained for path compatibility; it does not contain the manuscript text.
- [`crosscountry_20261113/causal/`](crosscountry_20261113/causal/): Chinese sample rules, official coverage evidence, report metadata, extraction products, estimators and sensitivity analyses.
- [`crosscountry_20261113/raw/`](crosscountry_20261113/raw/): attributed public-source material and macroeconomic inputs.
- [`crosscountry_20261113/results/`](crosscountry_20261113/results/): aggregate international results and policy context.
- [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md): persistent source links, attribution and redistribution boundaries.
- [`docs/SOURCE_RECONSTRUCTION.md`](docs/SOURCE_RECONSTRUCTION.md): optional report retrieval and reconstruction instructions.

## Licensed component

LSEG microdata and firm-level LSEG panels are excluded. Aggregate international tables and their analysis code are included. Users with the corresponding licensed source archive can place `environment_energy_metrics.parquet` and `reported_emissions.parquet` under `crosscountry_20261113/lseg/2000_2025/`, then run `python crosscountry_20261113/01_prepare.py` followed by `python crosscountry_20261113/02_analyze.py` from the repository root. The public-data results do not depend on these licensed inputs.

The complete company-report PDF corpus and full-page report excerpts are also excluded. Report URLs, filing dates, page references and hashes support source retrieval and inspection. Original source licenses remain applicable; see the data-source documentation.

## Citation

Please cite the manuscript and the original datasets relevant to the component reused. GitHub citation metadata are provided in [`CITATION.cff`](CITATION.cff). No journal acceptance or manuscript DOI is implied by this replication release.
