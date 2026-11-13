# Replication package

Talk, not numbers: entering China's emissions trading system and the carbon content of annual reports

Every table and figure in the paper is rebuilt by one command from the archived intermediate files. All inputs are public. No commercial database is used at any stage.

## One-command reproduction

```bash
bash run_all.sh
```

The script runs the unit tests, rebuilds the sample definition and the panel, regenerates every table into `out/tables/`, and redraws every figure into `out/figures/`. On a machine with the archived intermediate files in place it completes in a few minutes and exits with status 0.

Dependencies are listed in `requirements.txt` (Python 3.9 with pandas 2.3.3, numpy 2.0.2, statsmodels 0.14.6, scipy 1.13.1, PyMuPDF 1.26.5, pdfplumber 0.11.8, matplotlib 3.9.4, requests 2.32.5). To create the environment:

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
```

## Data sources and retrieval dates

| Data | Source | Retrieved | Scale |
|---|---|---|---|
| Annual report full text | CNINFO, the disclosure platform designated by the CSRC | August 2026 | 4,777 reports, 763 firms, FY2019–FY2025 |
| Key emitting entity roster | Ministry of Ecology and Environment | 18 July 2026 | 2,225 entities, compliance years 2019–2020 |
| Power sector allocation plans | Ministry of Ecology and Environment | 18 July 2026 | three documents covering 2019–2024 |
| Steel, cement and aluminum allocation plan | Ministry of Ecology and Environment | 18 July 2026 | compliance years 2024–2025 |
| Expansion work plan | Ministry of Ecology and Environment | 18 July 2026 | Huanqihou [2025] No. 23 |
| MOF Interim Provisions | Ministry of Finance | 18 July 2026 | Caikuai [2019] No. 22, web and PDF versions |
| Daily national carbon market quotations | Shanghai Environment and Energy Exchange | 31 July 2026 | 289 trading days, 27 May 2025 to 31 July 2026 |
| Financial statements and year-end market data | statements filed with the annual reports | August 2026 | non-missing above 99% on key items |

The annual report corpus is approximately 10 GB and is **not redistributed** with this package. `src/fetch_reports.py` retrieves it from CNINFO; the extraction products it feeds are archived here as `out/carbon_*.csv`, so the regressions and figures reproduce without it.

## Directory layout

```
raw/          Source data. policy/ holds the archived policy instruments;
              cea/ the daily carbon market quotations; firm/ financial and
              market data; esg/ the index of standalone sustainability reports;
              reports/ the annual report PDFs (not distributed).
src/          All scripts.
out/          Intermediate files and results. tables/ holds the paper's tables,
              figures/ its figures.
tests/        Unit tests.
_retired/     Superseded scripts, archived for provenance, not part of the
              reproduction path.
```

## Scripts and their outputs

| Script | Input | Output | Needs the PDF corpus |
|---|---|---|---|
| `fetch_reports.py` | CNINFO query interface | `raw/reports/*.pdf` | network |
| `fetch_cea.py` | exchange bulletins | `raw/cea/cea_daily.csv` | network |
| `fetch_esg_reports.py` | CNINFO search interface | `raw/esg/esg_index.csv` | network |
| `policy_parser.py` | `raw/policy/*.pdf` | `out/benchmark_power.csv`, `out/alpha_table.csv`, `out/key_emitters_2019_2020.csv` | no |
| `match_emitters.py` | roster and listed-firm register | `out/emitter_firm_match.csv` | no |
| `define_sample.py` | match results and industry classification | `out/sample_definition.csv` | no |
| `parse_carbon_disclosure.py` | annual report PDFs | `out/carbon_disclosure.csv` | yes |
| `parse_narrative.py` | annual report PDFs | `out/carbon_narrative.csv` | yes |
| `rescan_restricted.py` | flagged pages | `out/carbon_disclosure_restricted.csv` | yes |
| `rescan_namefilter.py` | restricted pages | `out/carbon_disclosure_namefilt.csv` | yes |
| `parse_operations.py` | annual report PDFs | `out/firm_operations.csv` | yes |
| `build_panel2.py` | the above | `out/panel2.csv` | no |
| `run_paper.py` | `out/*.csv` | `out/tables/tab1`–`tab11` | no |
| `run_paper2.py` | `out/*.csv` | `out/tables/tabA`–`tabD`, the two-event results | no |
| `run_valuation.py` | `out/panel2.csv` | `out/tables/tabF`, `tabG` | no |
| `make_paper_figs.py` | `out/tables/*.csv` | `out/figures/figure1`–`figure3` | no |

## Where each exhibit comes from

| Paper | File |
|---|---|
| Table 1, reports retrieved by group and year | `out/tables/tab1_sample.csv` |
| Table 2, sample construction | `out/tables/tab1_sample.csv` |
| Table 3, balance | `out/tables/tabE_balance_correct.csv` |
| Table 4, disclosure by group | `out/tables/tab3_descriptive.csv` |
| Table 5, entry and any carbon disclosure | `out/tables/tabA_main_two_events.csv` |
| Table 6, event studies | `out/tables/tabB_event_studies.csv` |
| Table 7, allowance quantity counts | `out/tables/tabD_quantity_counts.csv` |
| Table 8, pages retained by dictionary | `out/tables/tab8_dictionaries.csv` |
| Table 9, count outcome | `out/tables/tabA_main_two_events.csv` |
| Section 6 valuation tests | `out/tables/tabF_valuation.csv`, `tabG_exposure_diagnostics.csv` |
| Figure 1, the two margins | `out/figures/figure1_two_margins.*` |
| Figure 2, event studies | `out/figures/figure2_event_studies.*` |
| Figure 3, robustness | `out/figures/figure3_robustness.*` |

## The three keyword dictionaries

Page-level classification of carbon content uses three successively stricter rules. The paper reports all three.

1. **Original.** Terms include the compound for carbon emission allowance, the standalone term for quota, the acronym CEA, and terms for carbon trading, carbon asset and certified voluntary emission reduction. Retains 4,144 flagged pages.
2. **Restricted** (`rescan_restricted.py`). The standalone quota term counts only on pages that also carry an unambiguous carbon term, because it equally denotes production and trade quotas. CEA is matched with word boundaries and requires corroboration by a Chinese carbon term on the same page. Retains 3,156 pages.
3. **Restricted plus entity-name filter** (`rescan_namefilter.py`). A keyword occurrence is disregarded when it is immediately followed by the components of a Chinese company name, so that carbon-asset management subsidiaries appearing in related-party schedules do not count as disclosure. A page qualifies only if it carries at least one occurrence outside an entity name. Retains 2,754 pages.

Each rule is a strict tightening of the one before it, so a page can only lose its flag. Both scripts assert that monotonicity on every one of the 4,777 reports and exit non-zero if it is violated.

Keyword strings inside the code remain in Chinese because they are the patterns matched against the source documents. Everything else in the code is in English.

## Tests

```bash
./.venv/bin/python -m pytest tests/ -q
```

Coverage includes the policy parameter parsers (benchmark values checked cell by cell against the issued tables, the adjustment coefficient range, the roster size), the market data parser (four bulletin formats, and the separation of genuine zeros from missing values), the table and narrative separation, and the restricted dictionary rules.

## Known limitations

1. The 2024 cohort is defined from listed-firm industry classifications, while coverage attaches at the facility level, so the treatment definition is intention to treat.
2. The outcome is measured from annual reports only; standalone sustainability reports are outside the measure.
3. Hand validation covers precision on 30 flagged pages; recall and inter-coder agreement are not reported.
4. The exchange retains roughly fourteen months of daily quotations, so the carbon price series is shorter than the panel.
5. Narrative-level extraction covers FY2021–FY2025; the two years added later enter the panel through the page-level measures only.
