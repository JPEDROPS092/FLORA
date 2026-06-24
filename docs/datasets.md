# Datasets

FLORA supports direct download from three public microbiome repositories. All datasets used in development and testing target Brazilian and Amazonian biomes.

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
**Format:** BIOM / TSV
**Documentation:** https://www.earthmicrobiome.org/protocols-and-standards/

The EMP is a systematic characterization of microbial life on Earth, using standardized 16S rRNA amplicon protocols. FLORA integrates with the EMP portal to download per-study feature tables and metadata.

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
flora download mgnify MGYS00005116 --outdir data/raw --max-samples 80 \
    --to-duckdb --duckdb-path results/flora.duckdb

# SRA download (ENA fallback if sra-tools is missing) + DuckDB ingestion
flora download sra SRR7532201 SRR7532202 --outdir data/raw --jobs 4 \
    --to-duckdb --duckdb-path results/flora.duckdb
```

---

## Datasets Used in Development

### MGYS00005116 — Amazonian Forest Soils

| Field      | Value                         |
| ---------- | ----------------------------- |
| Repository | MGnify                        |
| Accession  | MGYS00005116                  |
| Biome      | Terrestrial / Tropical Forest |
| Region     | Brazilian Amazon              |
| Samples    | ~80                           |
| Target     | 16S rRNA V4 region            |
| Instrument | Illumina MiSeq                |

Download:

```python
from flora.io import MGnifyDownloader

dl = MGnifyDownloader(biome="root:Environmental:Terrestrial:Forest")
manifest = dl.fetch("MGYS00005116", output_dir="data/raw", max_samples=80)
```

```bash
flora download mgnify MGYS00005116 --outdir data/raw --max-samples 80
```

### SRP151124 — Brazilian Tropical Soil Microbiome

| Field      | Value                 |
| ---------- | --------------------- |
| Repository | NCBI SRA              |
| Accession  | SRP151124             |
| Biome      | Tropical Soil         |
| Region     | Brazil                |
| Samples    | ~60                   |
| Target     | 16S rRNA V3-V4 region |
| Instrument | Illumina HiSeq 2500   |

Download:

```python
from flora.io import NCBISRADownloader

# Uses sra-tools when available, otherwise falls back to ENA direct downloads
sra = NCBISRADownloader(n_jobs=4)
manifest = sra.fetch(["SRR7532201", "SRR7532202"], output_dir="data/raw")
```

```bash
flora download sra SRR7532201 SRR7532202 --outdir data/raw --jobs 4
```

### ERP009703 — Amazonian Rhizosphere

| Field      | Value                     |
| ---------- | ------------------------- |
| Repository | MGnify                    |
| Accession  | ERP009703                 |
| Biome      | Terrestrial / Rhizosphere |
| Region     | Brazilian Amazon          |
| Samples    | ~120                      |
| Target     | 16S rRNA V3-V4 region     |
| Instrument | Illumina MiSeq            |

Download:

```python
from flora.io import MGnifyDownloader

dl = MGnifyDownloader()
manifest = dl.fetch("ERP009703", output_dir="data/raw", max_samples=120)
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
