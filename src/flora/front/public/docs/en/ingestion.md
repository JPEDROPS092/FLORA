# 1 · Ingestion

Reconciles three files: **metadata**, **ASV table** and **taxonomy**.

## Preview

Before writing anything, the *Pipeline Studio* matches metadata against the table and classifies each sample:

| Status | When |
|---|---|
| `pass` | in both files, enough reads, group defined |
| `warn` | depth below the threshold or no group |
| `fail` | missing from a file or zero reads |

The threshold is the **rarefaction depth** set in the normalization step.

## Formats

- ASVs as **wide** TSV (samples × ASVs) or **long** (`sample_id`, `feature_id`, `abundance`), or BIOM.
- Extra metadata columns become available as comparison groups.

> FASTQ import, primer removal and denoising (QIIME2/DADA2) happen **outside** FLORA.
