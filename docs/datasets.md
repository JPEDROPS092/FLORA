# Datasets

FLORA supports direct download from public microbiome repositories. The library catalog in `src/flora/io/catalog_data/datasets.yaml` is the checked list. Three accessions that older notes called Amazonian are not: MGYS00005116 is vacuum-bag dust from the International Space Station, SRP151124 / PRJNA477418 is ectomycorrhizal fungi in recent forests (Belgium), and ERP009703 is the secondary accession of Ocean Sampling Day 2014 (PRJEB8682).

---

## Supported Repositories

### MGnify (EMBL-EBI)

**URL:** https://www.ebi.ac.uk/metagenomics/
**API:** https://www.ebi.ac.uk/metagenomics/api/v1/
**Format:** JSON REST API, returns TSV analysis results
**Documentation:** https://docs.mgnify.org/

MGnify is maintained by EMBL-EBI and provides analyzed metagenomics and amplicon datasets from environmental studies worldwide. FLORA queries the `/studies/{accession}/analyses` endpoint and downloads taxonomic summary files.

### NCBI SRA (Sequence Read Archive)

**URL:** https://www.ncbi.nlm.nih.gov/sra
**Tool:** sra-tools (`prefetch` + `fasterq-dump`), with automatic ENA fallback
**Format:** FASTQ (paired or single-end)
**Documentation:** https://www.ncbi.nlm.nih.gov/sra/docs/

SRA is the largest publicly available repository of high-throughput sequencing data. FLORA downloads raw FASTQ files via the `NCBISRADownloader`, which wraps `prefetch` and `fasterq-dump` from the NCBI sra-tools suite.

If `sra-tools` is not installed, `NCBISRADownloader` automatically falls back to direct FASTQ downloads from the [ENA Portal API](https://www.ebi.ac.uk/ena/portal/api/), so no external binaries are required. Set `allow_ena_fallback=False` to disable this and require `sra-tools` instead.

Reference: Katz et al. (2022). The Sequence Read Archive: a decade more of explosive growth and new challenges. *Nucleic Acids Research*, 50(D1), D387-D390. https://doi.org/10.1093/nar/gkab1053

### Earth Microbiome Project (EMP)

**URL:** https://www.earthmicrobiome.org/  
**Data portal:** https://qiita.ucsd.edu/emp/  
**Zenodo archive:** https://zenodo.org/record/890000  
**DOI:** https://doi.org/10.5281/zenodo.890000  
**Format:** BIOM / TSV  
**Documentation:** https://www.earthmicrobiome.org/protocols-and-standards/

The EMP is a systematic characterization of microbial life on Earth, using standardized 16S rRNA amplicon protocols. FLORA downloads the Release 1 data directly from Zenodo — no authentication required.

Files used by `EMPDownloader`:

| File | Size | Description |
|---|---|---|
| `emp_deblur_150bp.release1.biom` | 167 MB | Deblur-denoised OTU table (smallest available) |
| `emp_qiime_mapping_subset_2k_20170912.tsv` | 1.6 MB | Metadata for 2k-sample subset |
| `emp_observation_info_deblur.tar.gz` | 46 MB | Observation info including taxonomy |

Reference: Thompson et al. (2017). A communal catalogue reveals Earth's multiscale microbial diversity. *Nature*, 551, 457-463. https://doi.org/10.1038/nature24621

---

## Loading Downloads into DuckDB

Any `flora download` command can ingest the downloaded samples into a DuckDB
database immediately after the download finishes, using the `--to-duckdb` flag.

| Flag              | Default                  | Description                                      |
| ----------------- | ------------------------ | ------------------------------------------------ |
| `--to-duckdb`   | off                      | Ingest downloaded samples/metadata into DuckDB   |
| `--duckdb-path` | `results/flora.duckdb` | DuckDB file path used when`--to-duckdb` is set |

When ingesting, FLORA initializes the schema if needed and then:

- ingests `metadata.tsv` into the `samples` table when it is present, or
- creates minimal `samples` records (`sample_id` only) from `manifest.tsv` otherwise.

```bash
# MGnify download + DuckDB ingestion
flora download mgnify MGYS00001352 --outdir data/raw --max-samples 18 \
    --to-duckdb --duckdb-path results/flora.duckdb

# SRA download (ENA fallback if sra-tools is missing) + DuckDB ingestion
flora download sra SRR7532201 SRR7532202 --outdir data/raw --jobs 4 \
    --to-duckdb --duckdb-path results/flora.duckdb
```

---

## Datasets in the library

The Downloads page reads `datasets.yaml`. Counts below were checked on 2026-11-03. The one-click download does not pull whole-study FASTQ for shotgun archives.

| Accession | What it is | Samples | Seq | One-click download |
| --- | --- | --- | --- | --- |
| MGYS00005779 | Colombian Amazon land-use, soil | 64 | WGS | MGnify SSU table + sample metadata |
| MGYS00005810 | Amazon Continuum TPA assembly (PRJNA237344) | 83 (96 ENA runs) | WGS | MGnify SSU table + sample metadata |
| MGYS00000382 | Amazon Continuum primary metagenomes | 86 | WGS | metadata + SSU table if published |
| MGYS00004385 | Amazon River lake sediments | 29 | amplicon | MGnify SSU table + metadata |
| MGYS00001352 | Amazon deforestation soil | 18 | amplicon | metadata + SSU table if published |
| MGYS00006061 | Upper Amazon floodplain lakes | 3 | WGS | metadata + SSU table if published |
| MGYS00002298 | Manaus *Anopheles* breeding water | 48 | 16S amplicon | metadata + SSU table if published |
| MGYS00001713 | Atlantic Amazon coastal water | 2 | WGS | metadata + SSU table if published |
| MGYS00006055 | Carajás canga lakes (not the river channel) | 19 | WGS | metadata + SSU table |
| MGYS00004672 | Amazon plume and North Atlantic zooplankton | 33 | amplicon | metadata + SSU table if published |
| PRJEB8682 | Ocean Sampling Day 2014 (ERP009703) | 467 runs | amplicon + WGS | run metadata, not FASTQ |
| PRJEB1787 | Tara Oceans prokaryote shotgun | 249 runs | WGS | run metadata, not FASTQ |
| PRJEB402 | Tara Oceans barcoding and shotgun | 6423 runs | mixed | first 500 run records |
| PRJNA43021 | NIH Human Microbiome Project | 62860 runs | mixed | first 500 run records |
| EMP-R1 | Earth Microbiome Project Release 1 (Zenodo 890000, CC-BY-4.0) | 2000 in the subset file | 16S | BIOM deblur 150 bp + 2k metadata, capped at 200 samples |
| QIIME2-MP | QIIME 2 Moving Pictures tutorial | 34 | 16S V4 | metadata TSV + sequences + barcodes |
| MOTHUR-SOP | mothur MiSeq SOP zip | 20 | 16S V4 | miseqsopdata.zip |
| QIIME2-ATACAMA | QIIME 2 Atacama soil tutorial | 75 | amplicon | metadata + 10% FASTQ subset |
| SYNTHETIC | Local seeded cohort | 80 | simulated | metadata, ASV table, taxonomy |

```python
from flora.io import MGnifyDownloader

dl = MGnifyDownloader(biome="root:Environmental:Terrestrial:Soil")
manifest = dl.fetch("MGYS00001352", output_dir="data/raw", max_samples=18)
```

```bash
flora download mgnify MGYS00001352 --outdir data/raw --max-samples 18
```

```python
from flora.io import NCBISRADownloader

sra = NCBISRADownloader(n_jobs=4)
manifest = sra.fetch(["SRR2104526"], output_dir="data/raw")
```

---

## Reference Databases

### SILVA 138

Used by the QIIME 2 / DADA2 step for taxonomic classification.

**URL:** https://www.arb-silva.de/
**Version used:** SILVA 138.1
**Classifier file:** `silva-138-99-nb-classifier.qza`
**Download:** https://data.qiime2.org/2023.9/common/silva-138-99-nb-classifier.qza

Reference: Quast et al. (2013). The SILVA ribosomal RNA gene database project: improved data processing and web-based tools. *Nucleic Acids Research*, 41(D1), D590-D596. https://doi.org/10.1093/nar/gks1219

### Greengenes2

Alternative classifier available for QIIME 2.

**URL:** https://greengenes2.ucsd.edu/
**Reference:** McDonald et al. (2023). Greengenes2 unifies microbial data in a single reference tree. *Nature Biotechnology*, 41, 1330-1332. https://doi.org/10.1038/s41587-023-01845-1

---

## Data Format Standards

### BIOM

The Biological Observation Matrix (BIOM) format is the standard for storing OTU/ASV tables.

**Specification:** https://biom-format.org/
**Python library:** `biom-format`
Reference: McDonald et al. (2012). The Biological Observation Matrix (BIOM) format or: how I learned to stop worrying and love the ome-ome. *GigaScience*, 1(1), 7. https://doi.org/10.1186/2047-217X-1-7

### QIIME 2 Artifact Format (.qza)

FLORA reads `.qza` artifacts directly and exports them to Parquet via PyArrow.

**Documentation:** https://docs.qiime2.org/2024.2/concepts/

---

## Ethical and Access Notes

- All datasets listed above are publicly available without registration.
- MGnify and NCBI SRA data are released under open data policies that allow academic and commercial use with attribution.
- Always cite the original study associated with a dataset. The MGnify API returns study-level metadata including publication DOIs.
- Downloading large SRA datasets may require significant disk space and bandwidth. Use `--max-samples` or filter by run accession to limit scope.
