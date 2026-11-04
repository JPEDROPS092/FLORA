"""Command builders and result converters for the external workflows.

Everything that builds a command line or parses a tool's output is a pure function, so it is tested without the
tools installed. Execution lives in :mod:`flora.engines.jobs`.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

_RANK_PREFIX = {"d": "kingdom", "k": "kingdom", "p": "phylum", "c": "class", "o": "order", "f": "family", "g": "genus", "s": "species"}
_SILVA_OLD = re.compile(r"^D_(\d)__")
_OLD_ORDER = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
_SAFE_NUM = re.compile(r"^\d{1,5}$")


class WorkflowError(ValueError):
    """Invalid workflow parameters (reported to the user as-is)."""


def _int(params: dict[str, Any], key: str, default: int, lo: int = 0, hi: int = 100000) -> str:
    raw = params.get(key, default)
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise WorkflowError(f"{key} must be an integer") from exc
    if not lo <= value <= hi:
        raise WorkflowError(f"{key} must be between {lo} and {hi}")
    return str(value)


def _file(path: str | None, what: str) -> Path:
    if not path or not Path(path).is_file():
        raise WorkflowError(f"{what} não encontrado: {path or '(vazio)'}")
    return Path(path)


def qiime2_dada2_commands(manifest: str, out: Path, paired: bool, params: dict[str, Any], classifier: str | None, threads: int, build_tree: bool = False) -> list[list[str]]:
    """QIIME 2: import FASTQ manifest -> DADA2 -> (classify) -> (tree) -> export to ``out/export``."""
    _file(manifest, "Manifest")
    kind = "SampleData[PairedEndSequencesWithQuality]" if paired else "SampleData[SequencesWithQuality]"
    fmt = "PairedEndFastqManifestPhred33V2" if paired else "SingleEndFastqManifestPhred33V2"
    q = lambda name: str(out / name)  # noqa: E731
    denoise = ["qiime", "dada2", "denoise-paired" if paired else "denoise-single", "--i-demultiplexed-seqs", q("demux.qza"),
               "--p-trim-left-f", _int(params, "trim_left_f", 0, 0, 1000), "--p-trunc-len-f", _int(params, "trunc_len_f", 0, 0, 2000),
               "--p-n-threads", str(max(1, min(int(threads), 128))),
               "--o-table", q("table.qza"), "--o-representative-sequences", q("rep-seqs.qza"), "--o-denoising-stats", q("denoising-stats.qza")]
    if paired:
        denoise += ["--p-trim-left-r", _int(params, "trim_left_r", 0, 0, 1000), "--p-trunc-len-r", _int(params, "trunc_len_r", 0, 0, 2000)]
    cmds = [
        ["qiime", "tools", "import", "--type", kind, "--input-path", manifest, "--input-format", fmt, "--output-path", q("demux.qza")],
        denoise,
    ]
    export = out / "export"
    cmds.append(["qiime", "tools", "export", "--input-path", q("table.qza"), "--output-path", str(export / "table")])
    cmds.append(["qiime", "tools", "export", "--input-path", q("rep-seqs.qza"), "--output-path", str(export / "rep-seqs")])
    if classifier:
        _file(classifier, "Classificador (.qza)")
        cmds.append(["qiime", "feature-classifier", "classify-sklearn", "--i-classifier", classifier, "--i-reads", q("rep-seqs.qza"), "--o-classification", q("taxonomy.qza")])
        cmds.append(["qiime", "tools", "export", "--input-path", q("taxonomy.qza"), "--output-path", str(export / "taxonomy")])
    if build_tree:
        cmds.append(["qiime", "phylogeny", "align-to-tree-mafft-fasttree", "--i-sequences", q("rep-seqs.qza"), "--o-alignment", q("aligned.qza"),
                     "--o-masked-alignment", q("masked.qza"), "--o-tree", q("unrooted-tree.qza"), "--o-rooted-tree", q("rooted-tree.qza")])
        cmds.append(["qiime", "tools", "export", "--input-path", q("rooted-tree.qza"), "--output-path", str(export / "tree")])
    return cmds


def parse_lineage(text: str) -> dict[str, str]:
    """``d__Bacteria; p__X; …`` (or SILVA ``D_0__Bacteria;D_1__X``) -> rank columns."""
    out = {rank: "" for rank in ("kingdom", "phylum", "class", "order", "family", "genus", "species")}
    for i, part in enumerate(p.strip() for p in text.split(";") if p.strip()):
        old = _SILVA_OLD.match(part)
        if old:
            idx = int(old.group(1))
            if idx < len(_OLD_ORDER):
                out[_OLD_ORDER[idx]] = part[old.end():]
            continue
        m = re.match(r"^([a-z])__(.*)$", part)
        if m and m.group(1) in _RANK_PREFIX:
            out[_RANK_PREFIX[m.group(1)]] = m.group(2).strip()
        elif i < len(_OLD_ORDER):
            out[_OLD_ORDER[i]] = part
    return out


def convert_qiime_export(out: Path, metadata: str | None = None) -> dict[str, str]:
    """Turn ``export/table/feature-table.biom`` (+ ``export/taxonomy/taxonomy.tsv``) into FLORA's TSVs."""
    from biom import load_table

    biom_path = out / "export" / "table" / "feature-table.biom"
    if not biom_path.is_file():
        raise WorkflowError("O QIIME 2 não gerou feature-table.biom; veja o log do job.")
    table = load_table(str(biom_path))
    samples, features = list(table.ids("sample")), list(table.ids("observation"))
    matrix = table.matrix_data.T.tocsr()  # samples x features
    out.mkdir(parents=True, exist_ok=True)
    asv = out / "asv_table.tsv"
    with open(asv, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["sample_id", *features])
        for i, sid in enumerate(samples):
            w.writerow([sid, *[int(v) for v in matrix[i].toarray().ravel()]])
    paths = {"asv_table": str(asv)}
    tax_in = out / "export" / "taxonomy" / "taxonomy.tsv"
    if tax_in.is_file():
        tax = out / "taxonomy.tsv"
        with open(tax_in, encoding="utf-8", newline="") as src, open(tax, "w", encoding="utf-8", newline="") as dst:
            w = csv.writer(dst, delimiter="\t", lineterminator="\n")
            w.writerow(["feature_id", "kingdom", "phylum", "class", "order", "family", "genus", "species", "confidence"])
            for row in csv.DictReader(src, delimiter="\t"):
                lin = parse_lineage(row.get("Taxon", ""))
                w.writerow([row.get("Feature ID", ""), *[lin[k] for k in ("kingdom", "phylum", "class", "order", "family", "genus", "species")], row.get("Confidence", "")])
        paths["taxonomy"] = str(tax)
    meta = out / "metadata.tsv"
    if metadata and Path(metadata).is_file():
        meta.write_bytes(Path(metadata).read_bytes())
    else:
        meta.write_text("sample_id\n" + "".join(f"{s}\n" for s in samples), encoding="utf-8")
    paths["metadata"] = str(meta)
    return paths


# ---------------------------------------------------------------------------
# R workflows
# ---------------------------------------------------------------------------
_DADA2_R = r'''
suppressMessages(library(dada2))
args <- commandArgs(trailingOnly = TRUE)
fastq_dir <- args[1]; out_dir <- args[2]; ref_fasta <- args[3]
trunc_f <- as.integer(args[4]); trunc_r <- as.integer(args[5]); threads <- as.integer(args[6])
fwd <- sort(list.files(fastq_dir, pattern = "_R?1(_001)?\\.f(ast)?q(\\.gz)?$", full.names = TRUE))
rev <- sort(list.files(fastq_dir, pattern = "_R?2(_001)?\\.f(ast)?q(\\.gz)?$", full.names = TRUE))
if (length(fwd) == 0) stop("Nenhum FASTQ _1/_R1 encontrado em ", fastq_dir)
paired <- length(rev) == length(fwd)
samples <- sub("_R?1(_001)?\\.f(ast)?q(\\.gz)?$", "", basename(fwd))
filt_dir <- file.path(out_dir, "filtered"); dir.create(filt_dir, recursive = TRUE, showWarnings = FALSE)
ff <- file.path(filt_dir, paste0(samples, "_F.fastq.gz")); fr <- file.path(filt_dir, paste0(samples, "_R.fastq.gz"))
if (paired) { filt <- filterAndTrim(fwd, ff, rev, fr, truncLen = c(trunc_f, trunc_r), maxN = 0, maxEE = c(2, 2), truncQ = 2, multithread = threads)
} else { filt <- filterAndTrim(fwd, ff, truncLen = trunc_f, maxN = 0, maxEE = 2, truncQ = 2, multithread = threads) }
keep <- file.exists(ff); ff <- ff[keep]; fr <- fr[keep]; samples <- samples[keep]
errF <- learnErrors(ff, multithread = threads); dadaF <- dada(ff, err = errF, multithread = threads)
if (paired) { errR <- learnErrors(fr, multithread = threads); dadaR <- dada(fr, err = errR, multithread = threads)
  merged <- mergePairs(dadaF, ff, dadaR, fr); seqtab <- makeSequenceTable(merged)
} else { seqtab <- makeSequenceTable(dadaF) }
seqtab <- removeBimeraDenovo(seqtab, method = "consensus", multithread = threads)
rownames(seqtab) <- samples
ids <- sprintf("ASV_%05d", seq_len(ncol(seqtab)))
write.table(data.frame(sample_id = rownames(seqtab), setNames(as.data.frame(seqtab), ids), check.names = FALSE),
            file.path(out_dir, "asv_table.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)
writeLines(c(rbind(paste0(">", ids), colnames(seqtab))), file.path(out_dir, "rep-seqs.fasta"))
tax <- assignTaxonomy(colnames(seqtab), ref_fasta, multithread = threads)
tax <- cbind(feature_id = ids, as.data.frame(tax, stringsAsFactors = FALSE))
colnames(tax) <- tolower(colnames(tax)); if (!"species" %in% colnames(tax)) tax$species <- ""
write.table(tax[, c("feature_id", "kingdom", "phylum", "class", "order", "family", "genus", "species")], file.path(out_dir, "taxonomy.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)
'''

_ALDEX2_R = r'''
suppressMessages(library(ALDEx2))
args <- commandArgs(trailingOnly = TRUE)
asv <- read.delim(args[1], check.names = FALSE, row.names = 1); meta <- read.delim(args[2], check.names = FALSE)
col <- args[3]; a <- args[4]; b <- args[5]; out_file <- args[6]
sel <- meta[[col]] %in% c(a, b); ids <- meta[[1]][sel]; cond <- as.character(meta[[col]][sel])
counts <- t(asv[ids, , drop = FALSE])
x <- aldex(counts, cond, mc.samples = 128, test = "t", effect = TRUE, denom = "all")
res <- data.frame(feature_id = rownames(x), diff_btw = x$diff.btw, effect = x$effect, p = x$we.ep, q = x$we.eBH)
write.table(res, out_file, sep = "\t", quote = FALSE, row.names = FALSE)
'''


def dada2_r_command(fastq_dir: str, out: Path, ref_fasta: str, params: dict[str, Any], threads: int) -> tuple[list[str], str]:
    """Rscript command + script text for a DADA2 run over a folder of FASTQ files."""
    if not Path(fastq_dir).is_dir():
        raise WorkflowError(f"Pasta de FASTQ não encontrada: {fastq_dir}")
    _file(ref_fasta, "Banco de referência (FASTA do SILVA/GTDB para o DADA2)")
    cmd = ["Rscript", "--vanilla", str(out / "dada2.R"), fastq_dir, str(out), ref_fasta,
           _int(params, "trunc_len_f", 240, 0, 2000), _int(params, "trunc_len_r", 200, 0, 2000), str(max(1, min(int(threads), 128)))]
    return cmd, _DADA2_R


def aldex2_command(asv: str, metadata: str, column: str, a: str, b: str, out: Path) -> tuple[list[str], str]:
    _file(asv, "Tabela ASV")
    _file(metadata, "Metadata")
    for label, value in (("column", column), ("a", a), ("b", b)):
        if not value or "\n" in value:
            raise WorkflowError(f"{label} inválido")
    return ["Rscript", "--vanilla", str(out / "aldex2.R"), asv, metadata, column, a, b, str(out / "aldex2.tsv")], _ALDEX2_R


# ---------------------------------------------------------------------------
# More R workflows: ANCOM-BC2 and vegan
# ---------------------------------------------------------------------------
_ANCOMBC2_R = r'''
suppressMessages({ library(ANCOMBC); library(TreeSummarizedExperiment) })
args <- commandArgs(trailingOnly = TRUE)
asv <- read.delim(args[1], check.names = FALSE, row.names = 1); meta <- read.delim(args[2], check.names = FALSE, row.names = 1)
col <- args[3]; a <- args[4]; b <- args[5]; out_file <- args[6]
meta <- meta[meta[[col]] %in% c(a, b), , drop = FALSE]
meta[[col]] <- factor(meta[[col]], levels = c(a, b))
counts <- t(as.matrix(asv[rownames(meta), , drop = FALSE]))
tse <- TreeSummarizedExperiment(assays = list(counts = counts), colData = S4Vectors::DataFrame(meta))
res <- ancombc2(data = tse, assay_name = "counts", fix_formula = col, p_adj_method = "BH", prv_cut = 0.10,
                group = col, struc_zero = FALSE, neg_lb = FALSE, alpha = 0.05)$res
lfc <- res[[paste0("lfc_", col, b)]]
write.table(data.frame(feature_id = res$taxon, diff_btw = lfc, effect = lfc, p = res[[paste0("p_", col, b)]], q = res[[paste0("q_", col, b)]]),
            out_file, sep = "\t", quote = FALSE, row.names = FALSE)
'''

_VEGAN_R = r'''
suppressMessages(library(vegan))
args <- commandArgs(trailingOnly = TRUE)
asv <- read.delim(args[1], check.names = FALSE, row.names = 1); meta <- read.delim(args[2], check.names = FALSE, row.names = 1)
col <- args[3]; method <- args[4]; perms <- as.integer(args[5]); out_file <- args[6]
meta <- meta[rownames(asv), , drop = FALSE]; keep <- !is.na(meta[[col]]) & meta[[col]] != ""
asv <- asv[keep, , drop = FALSE]; grp <- factor(meta[[col]][keep])
d <- if (method == "jaccard") vegdist(asv, method = "jaccard", binary = TRUE) else if (method == "aitchison") {
  x <- log(as.matrix(asv) + 0.5); dist(x - rowMeans(x)) } else vegdist(decostand(asv, "total"), method = "bray")
ad <- adonis2(d ~ grp, permutations = perms)
bd <- betadisper(d, grp); pt <- permutest(bd, permutations = perms)
res <- data.frame(test = c("PERMANOVA (adonis2)", "PERMDISP (betadisper)"),
                  statistic = c(ad$F[1], pt$tab$F[1]), r2 = c(ad$R2[1], NA), p = c(ad$`Pr(>F)`[1], pt$tab$`Pr(>F)`[1]))
write.table(res, out_file, sep = "\t", quote = FALSE, row.names = FALSE)
'''

_VEGAN_METHODS = {"bray_curtis": "bray", "jaccard": "jaccard", "aitchison": "aitchison"}


def ancombc2_command(asv: str, metadata: str, column: str, a: str, b: str, out: Path) -> tuple[list[str], str]:
    _file(asv, "Tabela ASV")
    _file(metadata, "Metadata")
    for label, value in (("column", column), ("a", a), ("b", b)):
        if not value or "\n" in value:
            raise WorkflowError(f"{label} inválido")
    return ["Rscript", "--vanilla", str(out / "ancombc2.R"), asv, metadata, column, a, b, str(out / "ancombc2.tsv")], _ANCOMBC2_R


def vegan_command(asv: str, metadata: str, column: str, metric: str, permutations: int, out: Path) -> tuple[list[str], str]:
    _file(asv, "Tabela ASV")
    _file(metadata, "Metadata")
    if metric not in _VEGAN_METHODS:
        raise WorkflowError(f"Distância não suportada no vegan: {metric}. Use {', '.join(_VEGAN_METHODS)}.")
    if not column or "\n" in column:
        raise WorkflowError("column inválido")
    return ["Rscript", "--vanilla", str(out / "vegan.R"), asv, metadata, column, _VEGAN_METHODS[metric],
            _int({"p": permutations}, "p", 999, 99, 99999), str(out / "vegan.tsv")], _VEGAN_R


# ---------------------------------------------------------------------------
# cutadapt (primer removal) and VSEARCH (ASV -> OTU)
# ---------------------------------------------------------------------------
_PRIMER = re.compile(r"^[ACGTURYSWKMBDHVNacgturyswkmbdhvn]{10,60}$")
_FASTQ_R1 = re.compile(r"^(?P<sample>.+?)(?:_R?1)(?:_001)?\.f(?:ast)?q(?:\.gz)?$")


def _primer(value: str | None, label: str, required: bool = False) -> str | None:
    value = (value or "").strip()
    if not value:
        if required:
            raise WorkflowError(f"{label} é obrigatório")
        return None
    if not _PRIMER.match(value):
        raise WorkflowError(f"{label} deve ter só letras de DNA/IUPAC (10 a 60 bases)")
    return value.upper()


def cutadapt_commands(fastq_dir: str, out: Path, fwd_primer: str, rev_primer: str | None, threads: int) -> list[dict]:
    """One cutadapt call per sample (paired when a reverse primer is given). Output goes to ``out/trimmed``."""
    folder = Path(fastq_dir)
    if not folder.is_dir():
        raise WorkflowError(f"Pasta de FASTQ não encontrada: {fastq_dir}")
    g, G = _primer(fwd_primer, "Primer forward", required=True), _primer(rev_primer, "Primer reverse")
    files = sorted(p for p in folder.iterdir() if p.is_file())
    steps = []
    for f in files:
        m = _FASTQ_R1.match(f.name)
        if not m:
            continue
        sample = m.group("sample")
        r2 = next((p for p in files if p.name == f.name.replace("_R1", "_R2").replace("_1.", "_2.", 1) and p != f), None) if G else None
        trimmed = out / "trimmed"
        cmd = ["cutadapt", "-j", str(max(1, min(int(threads), 64))), "-g", g, "--discard-untrimmed", "-o", str(trimmed / f.name)]
        if G and r2:
            cmd += ["-G", G, "-p", str(trimmed / r2.name), str(f), str(r2)]
        else:
            cmd += [str(f)]
        steps.append({"label": f"cutadapt {sample}", "cmd": cmd})
    if not steps:
        raise WorkflowError("Nenhum FASTQ _R1/_1 encontrado na pasta.")
    return steps


def write_trimmed_manifest(out: Path) -> dict[str, str]:
    """QIIME 2 manifest (absolute paths) for the files cutadapt produced, ready for the qiime2-dada2 workflow."""
    trimmed = out / "trimmed"
    files = sorted(p for p in trimmed.iterdir() if p.is_file()) if trimmed.is_dir() else []
    rows = []
    for f in files:
        m = _FASTQ_R1.match(f.name)
        if m:
            r2 = next((p for p in files if p.name == f.name.replace("_R1", "_R2").replace("_1.", "_2.", 1) and p != f), None)
            rows.append((m.group("sample"), f, r2))
    if not rows:
        raise WorkflowError("O cutadapt não gerou nenhum arquivo; os primers podem não ter sido encontrados (--discard-untrimmed).")
    paired = all(r[2] for r in rows)
    manifest = out / "manifest.tsv"
    with open(manifest, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["sample-id", "forward-absolute-filepath"] + (["reverse-absolute-filepath"] if paired else []))
        for sample, f1, f2 in rows:
            w.writerow([sample, str(f1.resolve())] + ([str(f2.resolve())] if paired else []))
    return {"manifest": str(manifest), "trimmed_dir": str(trimmed)}


def vsearch_cluster_command(fasta: str, identity: float, out: Path, threads: int) -> list[str]:
    _file(fasta, "FASTA das sequências dos ASVs")
    if not 0.5 <= float(identity) <= 1.0:
        raise WorkflowError("identity deve estar entre 0,5 e 1,0")
    return ["vsearch", "--cluster_fast", fasta, "--id", f"{float(identity):.4f}", "--centroids", str(out / "otus.fasta"), "--uc", str(out / "clusters.uc"),
            "--threads", str(max(1, min(int(threads), 64)))]


def collapse_asv_to_otu(asv_tsv: Path, uc_file: Path, out: Path) -> dict[str, str]:
    """Sum ASV counts per VSEARCH cluster. ``.uc`` records: S = centroid, H = hit (query joins target's cluster)."""
    cluster_of: dict[str, str] = {}
    for line in uc_file.read_text(encoding="utf-8").splitlines():
        cols = line.split("\t")
        if cols[0] == "S":
            cluster_of[cols[8].split(";")[0]] = cols[8].split(";")[0]
        elif cols[0] == "H":
            cluster_of[cols[8].split(";")[0]] = cols[9].split(";")[0]
    if not cluster_of:
        raise WorkflowError("O VSEARCH não gerou clusters; confira se os cabeçalhos do FASTA são os IDs dos ASVs.")
    with open(asv_tsv, encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh, delimiter="\t")
        header = next(reader)
        features = header[1:]
        otus = sorted({cluster_of[f] for f in features if f in cluster_of})
        idx = {o: i for i, o in enumerate(otus)}
        rows = []
        for row in reader:
            sums = [0.0] * len(otus)
            for f, v in zip(features, row[1:], strict=False):
                if f in cluster_of and v not in ("", "0"):
                    sums[idx[cluster_of[f]]] += float(v)
            rows.append([row[0], *[int(x) if float(x).is_integer() else x for x in sums]])
    if not otus:
        raise WorkflowError("Nenhum ASV da tabela aparece no FASTA agrupado.")
    otu_path, map_path = out / "otu_table.tsv", out / "asv_to_otu.tsv"
    with open(otu_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["sample_id", *otus])
        w.writerows(rows)
    with open(map_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["asv", "otu"])
        w.writerows(sorted(cluster_of.items()))
    return {"otu_table": str(otu_path), "asv_to_otu": str(map_path), "otus_fasta": str(out / "otus.fasta"), "clusters": str(uc_file)}


def parse_diff_results(path: Path, limit: int = 200) -> dict[str, Any]:
    """Generic result table from an R workflow (``feature_id, diff_btw, effect, p, q`` or any TSV)."""
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        columns = list(reader.fieldnames or [])
        rows = [dict(r) for r in reader]

    def num(v: str | None) -> float | None:
        try:
            return float(v) if v not in (None, "", "NA", "NaN") else None
        except ValueError:
            return None

    if {"feature_id", "diff_btw", "q"} <= set(columns):
        rows.sort(key=lambda r: (num(r["q"]) is None, num(r["q"]) or 0.0))
    return {"columns": columns, "rows": rows[:limit], "total": len(rows)}


# ---------------------------------------------------------------------------
# QIIME 2 through its Python API
# ---------------------------------------------------------------------------
BRIDGE = Path(__file__).with_name("q2_bridge.py")


def qiime2_python_job(manifest: str, out: Path, paired: bool, params: dict[str, Any], classifier: str | None,
                      threads: int, build_tree: bool, python: str) -> tuple[dict[str, Any], list[str]]:
    """Spec for ``q2_bridge.py`` and the command that runs it with the QIIME 2 environment's Python."""
    _file(manifest, "Manifest")
    if classifier:
        _file(classifier, "Classificador (.qza)")
    spec = {
        "manifest": manifest, "out": str(out), "paired": paired, "classifier": classifier or None, "build_tree": build_tree,
        "threads": max(1, min(int(threads), 128)),
        "params": {k: int(_int(params, k, 0, 0, 2000)) for k in ("trim_left_f", "trunc_len_f", "trim_left_r", "trunc_len_r")},
    }
    return spec, [python, str(BRIDGE), str(out / "spec.json")]
