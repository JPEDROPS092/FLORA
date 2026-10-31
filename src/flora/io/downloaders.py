"""Public dataset downloaders for FLORA.

Provides downloaders for:
- MGnify (EMBL-EBI REST API) with biome filtering
- NCBI SRA via sra-tools (prefetch + fasterq-dump)
- Earth Microbiome Project (EMP) portal

All downloaders generate QIIME2-compatible manifests on completion and
validate downloads (file size, response codes) before reporting success.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm

from flora.core.exceptions import IngestionError

logger = logging.getLogger("flora.io.downloaders")

_MGNIFY_API = "https://www.ebi.ac.uk/metagenomics/api/v1"
_EMP_API = "https://qiita.ucsd.edu"


def _make_session(retries: int = 3, backoff: float = 1.0) -> requests.Session:
    """Create a requests Session with automatic retry on transient failures."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": "FLORA-Library/0.1.0"})
    return session


def _download_file(
    url: str,
    dest: Path,
    session: requests.Session | None = None,
    chunk_size: int = 65536,
    min_bytes: int = 100,
) -> Path:
    """Stream a file from url to dest with progress bar and size validation.

    Parameters
    ----------
    url : str
        Source URL.
    dest : Path
        Destination file path. Parent directories are created.
    session : requests.Session, optional
        Reuse an existing session (for auth and retry settings).
    chunk_size : int
        Download chunk size in bytes.
    min_bytes : int
        Minimum acceptable file size in bytes after download. Downloads
        below this threshold raise IngestionError (guards against HTML
        error pages saved as content).

    Returns
    -------
    Path
        Resolved path to the downloaded file.

    Raises
    ------
    IngestionError
        If the HTTP request fails or the downloaded file is too small.
    """
    sess = session or _make_session()
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        resp = sess.get(url, stream=True, timeout=120)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise IngestionError(f"HTTP request failed for {url}: {exc}", source=url) from exc

    total = int(resp.headers.get("content-length", 0))
    with open(dest, "wb") as fh, tqdm(
        total=total or None,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
        desc=dest.name,
        leave=False,
    ) as pbar:
        for chunk in resp.iter_content(chunk_size=chunk_size):
            if chunk:
                fh.write(chunk)
                pbar.update(len(chunk))

    size = dest.stat().st_size
    if size < min_bytes:
        dest.unlink(missing_ok=True)
        raise IngestionError(
            f"Downloaded file is too small ({size} bytes): likely an error page. URL: {url}",
            source=url,
        )

    logger.debug("Downloaded %s -> %s (%d bytes)", url, dest, size)
    return dest


def _write_manifest(output_dir: Path, samples: list[dict], paired_end: bool = True) -> Path:
    """Write a QIIME2 manifest TSV.

    Parameters
    ----------
    output_dir : Path
        Directory for the manifest file.
    samples : list of dict
        Each dict must have keys: sample_id, forward (and reverse if paired).
    paired_end : bool
        If True, write paired-end manifest format.

    Returns
    -------
    Path
        Path to the written manifest.tsv.
    """
    manifest_path = output_dir / "manifest.tsv"
    with open(manifest_path, "w", encoding="utf-8") as fh:
        if paired_end:
            fh.write("sample-id\tforward-absolute-filepath\treverse-absolute-filepath\n")
            for s in samples:
                fh.write(f"{s['sample_id']}\t{s['forward']}\t{s.get('reverse', '')}\n")
        else:
            fh.write("sample-id\tabsolute-filepath\n")
            for s in samples:
                fh.write(f"{s['sample_id']}\t{s['forward']}\n")
    logger.info("Manifest written: %s (%d samples)", manifest_path, len(samples))
    return manifest_path


def _as_lower_text(value: object) -> str:
    """Safely coerce an arbitrary API value to lowercase text.

    MGnify attribute fields are not always plain strings; they may arrive as
    dict/list/null depending on endpoint and payload shape.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value.lower()
    if isinstance(value, dict):
        parts: list[str] = []
        for candidate_key in ("name", "label", "description", "id", "value"):
            candidate = value.get(candidate_key)
            if isinstance(candidate, str) and candidate.strip():
                parts.append(candidate)
        if parts:
            return " ".join(parts).lower()
        return " ".join(str(v) for v in value.values() if v is not None).lower()
    if isinstance(value, (list, tuple, set)):
        return " ".join(str(v) for v in value if v is not None).lower()
    return str(value).lower()


# ---------------------------------------------------------------------------
# MGnify downloader
# ---------------------------------------------------------------------------

@dataclass
class MGnifyDownloader:
    """Download FASTQ files and metadata from MGnify (EMBL-EBI).

    Uses the MGnify REST API v1. No authentication required for public studies.

    Parameters
    ----------
    biome : str
        Biome path filter (e.g. ``"root:Environmental:Terrestrial:Forest"``).
    api_base : str
        MGnify API base URL. Override for testing.
    request_delay : float
        Seconds to wait between API calls to respect rate limits.

    Examples
    --------
    >>> dl = MGnifyDownloader(biome="root:Environmental:Terrestrial:Forest")
    >>> manifest = dl.fetch("MGYS00005116", output_dir="data/raw", max_samples=20)
    """

    biome: str = "root:Environmental:Terrestrial"
    api_base: str = _MGNIFY_API
    request_delay: float = 0.5

    def _api_get(self, session: requests.Session, url: str) -> dict:
        """GET a JSON response from the MGnify API with error handling."""
        logger.debug("GET %s", url)
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            raise IngestionError(f"MGnify API request failed: {exc}", source=url) from exc

    def _iter_paginated(
        self, session: requests.Session, url: str
    ) -> Iterator[dict]:
        """Iterate over all pages of a MGnify paginated endpoint."""
        current = url
        while current:
            data = self._api_get(session, current)
            for item in data.get("data", []):
                yield item
            current = data.get("links", {}).get("next")
            if current:
                time.sleep(self.request_delay)

    def _get_sample_runs(
        self, session: requests.Session, sample_accession: str
    ) -> list[dict]:
        """Return download info for paired FASTQ files for a sample."""
        url = f"{self.api_base}/samples/{sample_accession}/runs"
        try:
            data = self._api_get(session, url)
        except IngestionError:
            return []

        downloads = []
        for run in data.get("data", []):
            run_id = run.get("id", "")
            dl_url = f"{self.api_base}/runs/{run_id}/downloads"
            try:
                dl_data = self._api_get(session, dl_url)
            except IngestionError:
                continue
            time.sleep(self.request_delay)

            for item in dl_data.get("data", []):
                attrs = item.get("attributes", {})
                fmt = attrs.get("file-format", {}).get("name", "")
                dl_link = attrs.get("url", "")
                if fmt == "FASTQ" and dl_link:
                    downloads.append({
                        "run_id": run_id,
                        "sample_id": sample_accession,
                        "url": dl_link,
                        "description": _as_lower_text(attrs.get("description")),
                    })
        return downloads

    def fetch(
        self,
        study_accession: str,
        output_dir: str | Path,
        max_samples: int = 100,
        paired_end: bool = True,
        skip_existing: bool = True,
    ) -> Path:
        """Download FASTQ files for a MGnify study.

        Parameters
        ----------
        study_accession : str
            MGnify study accession (e.g. ``"MGYS00005116"``).
        output_dir : str or Path
            Root directory. Creates: fastq/, metadata.tsv, manifest.tsv.
        max_samples : int
            Maximum samples to download.
        paired_end : bool
            Only download paired-end runs.
        skip_existing : bool
            Skip download if destination file already exists.

        Returns
        -------
        Path
            Path to the generated manifest.tsv.

        Raises
        ------
        IngestionError
            If the API is unreachable or no samples are found.
        """
        out = Path(output_dir)
        fastq_dir = out / "fastq"
        fastq_dir.mkdir(parents=True, exist_ok=True)
        session = _make_session()

        logger.info("Fetching MGnify study %s (max=%d)", study_accession, max_samples)
        study_url = f"{self.api_base}/studies/{study_accession}/samples"
        samples = list(self._iter_paginated(session, study_url))[:max_samples]

        if not samples:
            raise IngestionError(
                f"No samples found for study {study_accession}",
                source=study_accession,
            )

        manifest_rows: list[dict] = []
        metadata_rows: list[dict] = []

        for sample in tqdm(samples, desc=f"Processing {study_accession}"):
            sample_acc = sample.get("id", "")
            attrs = sample.get("attributes", {})
            downloads = self._get_sample_runs(session, sample_acc)

            r1_path: str | None = None
            r2_path: str | None = None

            for dl in downloads:
                url = dl["url"]
                fname = url.split("/")[-1].split("?")[0] or f"{sample_acc}_{dl['run_id']}.fastq.gz"
                dest = fastq_dir / fname

                desc = dl["description"]
                is_forward = any(k in desc for k in ("forward", "_1", "_r1")) or "_1." in fname or "_R1" in fname
                is_reverse = any(k in desc for k in ("reverse", "_2", "_r2")) or "_2." in fname or "_R2" in fname

                if skip_existing and dest.exists() and dest.stat().st_size > 100:
                    logger.debug("Skipping existing: %s", dest)
                else:
                    try:
                        _download_file(url, dest, session=session)
                    except IngestionError as exc:
                        logger.warning("Download failed for %s: %s", url, exc)
                        continue

                if is_forward:
                    r1_path = str(dest.resolve())
                elif is_reverse:
                    r2_path = str(dest.resolve())
                elif not r1_path:
                    r1_path = str(dest.resolve())

            if paired_end and r1_path and r2_path:
                manifest_rows.append({
                    "sample_id": sample_acc,
                    "forward": r1_path,
                    "reverse": r2_path,
                })
            elif not paired_end and r1_path:
                manifest_rows.append({
                    "sample_id": sample_acc,
                    "forward": r1_path,
                })

            geo = attrs.get("geo-loc-name", "")
            metadata_rows.append({
                "sample_id": sample_acc,
                "biome": attrs.get("biome", {}).get("id", self.biome) if isinstance(attrs.get("biome"), dict) else str(attrs.get("biome", self.biome)),
                "location": geo,
                "latitude": str(attrs.get("latitude", "")),
                "longitude": str(attrs.get("longitude", "")),
            })

        self._write_metadata(out, metadata_rows)
        manifest = _write_manifest(out, manifest_rows, paired_end=paired_end)
        logger.info(
            "MGnify fetch complete: %d samples in manifest, output=%s",
            len(manifest_rows),
            out,
        )
        return manifest

    def _write_metadata(self, output_dir: Path, rows: list[dict]) -> None:
        if not rows:
            return
        meta_path = output_dir / "metadata.tsv"
        keys = list(rows[0].keys())
        with open(meta_path, "w", encoding="utf-8") as fh:
            fh.write("\t".join(keys) + "\n")
            for row in rows:
                fh.write("\t".join(str(row.get(k, "")) for k in keys) + "\n")
        logger.info("Metadata written: %s (%d samples)", meta_path, len(rows))

    def fetch_analyses(
        self,
        study_accession: str,
        output_dir: str | Path,
        max_analyses: int = 5,
    ) -> dict[str, Path]:
        """Download pre-computed OTU table and taxonomy from MGnify analyses.

        Queries the MGnify analyses endpoint, downloads the first available
        OTU table TSV and taxonomy TSV, and writes them as ``asv_table.tsv``
        and ``taxonomy.tsv`` ready for ``FLORAPipeline``.

        Parameters
        ----------
        study_accession : str
            MGnify study accession (e.g. ``"MGYS00005116"``).
        output_dir : str or Path
            Directory to write output files.
        max_analyses : int
            Maximum number of analyses to inspect when searching for files.

        Returns
        -------
        dict
            Keys: ``"asv_table"``, ``"taxonomy"``, ``"metadata"`` — Path objects.

        Raises
        ------
        IngestionError
            If no OTU table or taxonomy file is found for the study.
        """
        import csv
        import io

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        session = _make_session()

        url = f"{self.api_base}/studies/{study_accession}/analyses"
        logger.info(
            "Fetching MGnify analyses for study=%s from %s (limit=%d)",
            study_accession,
            url,
            max_analyses,
        )
        analyses = list(self._iter_paginated(session, url))[:max_analyses]

        if not analyses:
            raise IngestionError(
                f"No analyses found for study {study_accession}",
                source=study_accession,
            )

        logger.info(
            "Found %d analyses to inspect for study=%s",
            len(analyses),
            study_accession,
        )

        asv_rows: dict[str, dict] = {}   # sample_id -> {feature_id: count}
        tax_rows: dict[str, dict] = {}   # feature_id -> lineage dict
        metadata_rows: list[dict] = []

        for analysis in tqdm(analyses, desc=f"Analyses {study_accession}"):
            acc = analysis.get("id", "")
            logger.info("Inspecting analysis=%s", acc)
            rels = analysis.get("relationships", {})
            sample_acc = (
                rels.get("sample", {}).get("data", {}).get("id", acc)
                if isinstance(rels.get("sample", {}).get("data"), dict)
                else acc
            )

            dl_url = f"{self.api_base}/analyses/{acc}/downloads"
            try:
                dl_data = self._api_get(session, dl_url)
            except IngestionError:
                logger.warning("Could not fetch downloads for analysis=%s", acc)
                continue
            time.sleep(self.request_delay)

            otu_url: str | None = None
            tax_url: str | None = None
            available_downloads: list[str] = []

            for item in dl_data.get("data", []):
                attrs = item.get("attributes", {})
                alias = _as_lower_text(attrs.get("alias"))
                desc  = _as_lower_text(attrs.get("description"))
                link  = attrs.get("url", "")
                fmt   = _as_lower_text(attrs.get("file-format", {}).get("name", ""))
                available_downloads.append(
                    f"alias={alias or '-'} | format={fmt or '-'} | description={desc or '-'}"
                )

                is_tsv = fmt in ("tsv", "csv", "text") or link.endswith(".tsv") or link.endswith(".txt")
                if not is_tsv:
                    continue

                if otu_url is None and any(
                    k in alias or k in desc
                    for k in ("otu table", "asv table", "reads ssu", "sequences ssu")
                ):
                    otu_url = link

                if tax_url is None and any(
                    k in alias or k in desc
                    for k in ("taxonom", "tax assign", "ssu rrna")
                ):
                    tax_url = link

            logger.info(
                "Analysis=%s sample=%s otu=%s taxonomy=%s",
                acc,
                sample_acc,
                "yes" if otu_url else "no",
                "yes" if tax_url else "no",
            )
            if not otu_url and not tax_url and available_downloads:
                logger.warning(
                    "Analysis=%s exposes downloads, but none matched FLORA's OTU/taxonomy filters: %s",
                    acc,
                    " || ".join(available_downloads),
                )
            elif not available_downloads:
                logger.warning("Analysis=%s returned no downloadable files", acc)

            # Download OTU table
            if otu_url:
                try:
                    logger.info("Downloading OTU table for analysis=%s", acc)
                    resp = session.get(otu_url, timeout=60)
                    resp.raise_for_status()
                    reader = csv.DictReader(
                        io.StringIO(resp.text), delimiter="\t"
                    )
                    for row in reader:
                        feature_id = row.get("#OTU ID") or row.get("OTU ID") or row.get("feature-id") or list(row.values())[0]
                        count = row.get(sample_acc) or row.get(acc) or "0"
                        if sample_acc not in asv_rows:
                            asv_rows[sample_acc] = {}
                        asv_rows[sample_acc][feature_id] = count
                    logger.info("Loaded OTU data for sample=%s from analysis=%s", sample_acc, acc)
                except Exception as exc:
                    logger.warning("OTU table download failed for %s: %s", acc, exc)

            # Download taxonomy
            if tax_url and not tax_rows:
                try:
                    logger.info("Downloading taxonomy table for analysis=%s", acc)
                    resp = session.get(tax_url, timeout=60)
                    resp.raise_for_status()
                    reader = csv.DictReader(
                        io.StringIO(resp.text), delimiter="\t"
                    )
                    for row in reader:
                        feature_id = row.get("#OTU ID") or row.get("OTU ID") or row.get("feature-id") or list(row.values())[0]
                        lineage = row.get("taxonomy") or row.get("Taxon") or row.get("lineage") or ""
                        ranks = [r.strip() for r in lineage.split(";")]
                        tax_rows[feature_id] = {
                            "feature_id": feature_id,
                            "kingdom":  ranks[0] if len(ranks) > 0 else "",
                            "phylum":   ranks[1] if len(ranks) > 1 else "",
                            "class":    ranks[2] if len(ranks) > 2 else "",
                            "order":    ranks[3] if len(ranks) > 3 else "",
                            "family":   ranks[4] if len(ranks) > 4 else "",
                            "genus":    ranks[5] if len(ranks) > 5 else "",
                            "species":  ranks[6] if len(ranks) > 6 else "",
                        }
                    logger.info("Loaded taxonomy rows: %d", len(tax_rows))
                except Exception as exc:
                    logger.warning("Taxonomy download failed for %s: %s", acc, exc)

            # Fetch sample metadata
            try:
                logger.info("Fetching sample metadata for sample=%s", sample_acc)
                meta_resp = session.get(
                    f"{self.api_base}/samples/{sample_acc}", timeout=30
                )
                meta_resp.raise_for_status()
                attrs = meta_resp.json().get("data", {}).get("attributes", {})
                metadata_rows.append({
                    "sample_id": sample_acc,
                    "biome": str(attrs.get("biome", self.biome)),
                    "location": attrs.get("geo-loc-name", ""),
                    "latitude": str(attrs.get("latitude", "")),
                    "longitude": str(attrs.get("longitude", "")),
                })
            except Exception:
                metadata_rows.append({"sample_id": sample_acc, "biome": self.biome,
                                       "location": "", "latitude": "", "longitude": ""})
            time.sleep(self.request_delay)

        if not asv_rows:
            raise IngestionError(
                f"No OTU table data found for study {study_accession}. "
                "The study may not have pre-computed analyses available, or the available "
                "downloads may not expose TSV OTU/ASV tables compatible with FLORA.",
                source=study_accession,
            )

        # Write asv_table.tsv (wide: samples x features)
        all_features = sorted({f for counts in asv_rows.values() for f in counts})
        asv_path = out / "asv_table.tsv"
        with open(asv_path, "w", encoding="utf-8") as fh:
            fh.write("sample_id\t" + "\t".join(all_features) + "\n")
            for sample_id, counts in asv_rows.items():
                row = [sample_id] + [counts.get(f, "0") for f in all_features]
                fh.write("\t".join(row) + "\n")
        logger.info("ASV table written: %s (%d samples x %d features)", asv_path, len(asv_rows), len(all_features))

        # Write taxonomy.tsv
        tax_path = out / "taxonomy.tsv"
        tax_cols = ["feature_id", "kingdom", "phylum", "class", "order", "family", "genus", "species"]
        with open(tax_path, "w", encoding="utf-8") as fh:
            fh.write("\t".join(tax_cols) + "\n")
            for row in tax_rows.values():
                fh.write("\t".join(row.get(c, "") for c in tax_cols) + "\n")
        logger.info("Taxonomy written: %s", tax_path)

        # Write metadata.tsv
        self._write_metadata(out, metadata_rows)

        return {
            "asv_table": asv_path,
            "taxonomy": tax_path,
            "metadata": out / "metadata.tsv",
        }

    def list_studies(self, max_results: int = 20) -> list[dict]:
        """List public MGnify studies matching this downloader's biome.

        Parameters
        ----------
        max_results : int
            Maximum number of studies to return.

        Returns
        -------
        list of dict
            Each dict contains: id, biome, samples_count, last_update.
        """
        session = _make_session()
        biome_escaped = self.biome.replace(":", "%3A")
        url = f"{self.api_base}/biomes/{biome_escaped}/studies"
        studies = []
        for item in self._iter_paginated(session, url):
            if len(studies) >= max_results:
                break
            attrs = item.get("attributes", {})
            studies.append({
                "id": item.get("id"),
                "biome": attrs.get("biome-id", ""),
                "samples_count": attrs.get("samples-count", 0),
                "last_update": attrs.get("last-update", ""),
            })
        return studies


# ---------------------------------------------------------------------------
# NCBI SRA downloader
# ---------------------------------------------------------------------------

@dataclass
class NCBISRADownloader:
    """Download FASTQ files from NCBI SRA using sra-tools.

    Requires ``prefetch`` and ``fasterq-dump`` in the system PATH.
    Install from: https://github.com/ncbi/sra-tools/wiki/01.-Downloading-SRA-Toolkit

    Parameters
    ----------
    n_jobs : int
        Threads for fasterq-dump.
    max_size : str
        Maximum download size per accession (passed to prefetch --max-size).
    temp_dir : str or Path, optional
        Temporary directory for SRA cache files.

    Examples
    --------
    >>> dl = NCBISRADownloader(n_jobs=4)
    >>> manifest = dl.fetch(["SRR12345678"], output_dir="data/raw")
    """

    n_jobs: int = 4
    max_size: str = "50G"
    temp_dir: str | Path | None = None

    def _check_tools(self) -> None:
        """Verify sra-tools are installed and accessible."""
        missing = []
        for tool in ("prefetch", "fasterq-dump"):
            result = subprocess.run(
                ["which", tool], capture_output=True, text=True
            )
            if result.returncode != 0:
                missing.append(tool)
        if missing:
            raise IngestionError(
                f"sra-tools not found: {missing}. "
                "Install from https://github.com/ncbi/sra-tools",
                context={"missing": missing},
            )

    def _run(self, cmd: list[str], desc: str) -> subprocess.CompletedProcess:
        """Run a shell command with logging."""
        logger.debug("Running: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("%s failed: %s", desc, result.stderr[-500:])
        return result

    def fetch(
        self,
        accessions: list[str],
        output_dir: str | Path,
        skip_existing: bool = True,
    ) -> Path:
        """Download FASTQ files for a list of SRR/ERR/DRR accessions.

        Parameters
        ----------
        accessions : list of str
            SRR, ERR, or DRR accession IDs.
        output_dir : str or Path
            Root directory for downloads.
        skip_existing : bool
            Skip accessions whose FASTQ files are already present.

        Returns
        -------
        Path
            Path to the generated manifest.tsv.

        Raises
        ------
        IngestionError
            If sra-tools is not installed.
        """
        self._check_tools()
        out = Path(output_dir)
        fastq_dir = out / "fastq"
        fastq_dir.mkdir(parents=True, exist_ok=True)

        sra_cache = Path(self.temp_dir) if self.temp_dir else out / ".sra_cache"
        sra_cache.mkdir(parents=True, exist_ok=True)

        manifest_rows: list[dict] = []

        for acc in tqdm(accessions, desc="Downloading SRA"):
            r1 = fastq_dir / f"{acc}_1.fastq"
            r2 = fastq_dir / f"{acc}_2.fastq"
            r1_gz = fastq_dir / f"{acc}_1.fastq.gz"
            r2_gz = fastq_dir / f"{acc}_2.fastq.gz"

            if skip_existing and (r1.exists() or r1_gz.exists()):
                logger.info("Skipping existing: %s", acc)
                fwd = str(r1.resolve()) if r1.exists() else str(r1_gz.resolve())
                rev = str(r2.resolve()) if r2.exists() else (str(r2_gz.resolve()) if r2_gz.exists() else "")
                manifest_rows.append({
                    "sample_id": acc,
                    "forward": fwd,
                    "reverse": rev,
                })
                continue

            logger.info("Prefetching %s", acc)
            prefetch_result = self._run(
                ["prefetch", "--max-size", self.max_size, "-O", str(sra_cache), acc],
                desc=f"prefetch {acc}",
            )
            if prefetch_result.returncode != 0:
                logger.error("prefetch failed for %s, skipping", acc)
                continue

            logger.info("Converting %s to FASTQ", acc)
            sra_file = sra_cache / acc / f"{acc}.sra"
            if not sra_file.exists():
                sra_file = sra_cache / f"{acc}.sra"

            fqdump_cmd = [
                "fasterq-dump",
                "--split-files",
                "--threads", str(self.n_jobs),
                "--outdir", str(fastq_dir),
                str(sra_file) if sra_file.exists() else acc,
            ]
            fd_result = self._run(fqdump_cmd, desc=f"fasterq-dump {acc}")
            if fd_result.returncode != 0:
                logger.error("fasterq-dump failed for %s", acc)
                continue

            fwd_path = r1.resolve() if r1.exists() else (r1_gz.resolve() if r1_gz.exists() else None)
            rev_path = r2.resolve() if r2.exists() else (r2_gz.resolve() if r2_gz.exists() else None)

            if fwd_path:
                manifest_rows.append({
                    "sample_id": acc,
                    "forward": str(fwd_path),
                    "reverse": str(rev_path) if rev_path else "",
                })
            else:
                logger.warning("No FASTQ output found for %s", acc)

        manifest = _write_manifest(out, manifest_rows, paired_end=True)
        logger.info("SRA fetch complete: %d/%d accessions in manifest", len(manifest_rows), len(accessions))
        return manifest

    @staticmethod
    def search_accessions(
        query: str,
        max_results: int = 50,
        organism: str = "bacteria",
    ) -> list[str]:
        """Search NCBI SRA for accession IDs matching a query.

        Uses the NCBI Entrez API (no API key required for low-volume queries).

        Parameters
        ----------
        query : str
            Search terms (e.g. ``"16S Amazon soil metagenomics"``).
        max_results : int
            Maximum number of accessions to return.
        organism : str
            Organism filter added to the query.

        Returns
        -------
        list of str
            SRR accession IDs.
        """
        import xml.etree.ElementTree as ET

        esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {
            "db": "sra",
            "term": f"{query} AND {organism}[organism]",
            "retmax": max_results,
            "retmode": "json",
        }
        try:
            resp = requests.get(esearch_url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            ids = data.get("esearchresult", {}).get("idlist", [])
        except Exception as exc:
            logger.error("NCBI Entrez search failed: %s", exc)
            return []

        if not ids:
            return []

        efetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        params2 = {"db": "sra", "id": ",".join(ids), "rettype": "runinfo", "retmode": "text"}
        try:
            resp2 = requests.get(efetch_url, params=params2, timeout=30)
            resp2.raise_for_status()
        except Exception as exc:
            logger.error("NCBI Entrez fetch failed: %s", exc)
            return []

        accessions = []
        for line in resp2.text.splitlines()[1:]:
            cols = line.split(",")
            if cols and cols[0].startswith(("SRR", "ERR", "DRR")):
                accessions.append(cols[0])

        return accessions[:max_results]


# ---------------------------------------------------------------------------
# EMP downloader
# ---------------------------------------------------------------------------

# Earth Microbiome Project Release 1 — Zenodo archive (no auth required)
# Thompson et al. 2017, Nature 551. https://doi.org/10.5281/zenodo.890000
# Taxonomy is embedded in the BIOM observation metadata — no separate download needed.
_EMP_ZENODO = "https://zenodo.org/record/890000/files"
_EMP_FILES = {
    # Smallest BIOM available (deblur 150bp, 167 MB) — taxonomy in obs metadata
    "biom":     f"{_EMP_ZENODO}/emp_deblur_150bp.release1.biom?download=1",
    # QC-filtered 2k subset metadata (1.6 MB) — recommended for quick-start
    "metadata": f"{_EMP_ZENODO}/emp_qiime_mapping_subset_2k_20170912.tsv?download=1",
}


@dataclass
class EMPDownloader:
    """Download data from the Earth Microbiome Project (Release 1).

    Downloads the OTU table (BIOM), metadata, and taxonomy directly from
    ``data.microbio.me``. No authentication is required.

    The full EMP dataset contains 30,000+ samples. Use ``biome_filter`` and
    ``max_samples`` to extract a manageable subset.

    Parameters
    ----------
    biome_filter : str or None
        Case-insensitive substring to match against the ``empo_3`` or
        ``env_biome`` metadata column (e.g. ``"forest"``). If None, all
        samples are kept.

    Examples
    --------
    >>> dl = EMPDownloader(biome_filter="forest")
    >>> files = dl.fetch(output_dir="data/raw/emp", max_samples=200)
    """

    biome_filter: str | None = None

    def fetch(
        self,
        output_dir: str | Path,
        max_samples: int = 500,
        skip_existing: bool = True,
    ) -> dict[str, Path]:
        """Download and prepare EMP data for FLORA.

        Steps:
        1. Download BIOM, metadata, and taxonomy from data.microbio.me.
        2. Filter samples by ``biome_filter`` (optional).
        3. Subset to ``max_samples`` samples.
        4. Convert BIOM → wide TSV (``asv_table.tsv``).
        5. Normalise taxonomy to FLORA schema (``taxonomy.tsv``).

        Parameters
        ----------
        output_dir : str or Path
            Destination directory. Created if it does not exist.
        max_samples : int
            Maximum number of samples to include.
        skip_existing : bool
            If the destination files already exist, skip the download step.

        Returns
        -------
        dict
            Keys: ``"asv_table"``, ``"taxonomy"``, ``"metadata"`` — Paths.
        """
        try:
            import biom as biom_lib
        except ImportError as exc:
            raise IngestionError(
                "biom-format is required for EMPDownloader. "
                "Install with: conda install -c conda-forge biom-format",
            ) from exc

        import pandas as pd

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        session = _make_session()

        raw_biom     = out / "emp_deblur_150bp.release1.biom"
        raw_metadata = out / "emp_metadata_raw.tsv"

        # 1. Download raw files (skip if already present)
        for dest, url, label in [
            (raw_biom,     _EMP_FILES["biom"],     "BIOM table (~167 MB)"),
            (raw_metadata, _EMP_FILES["metadata"], "metadata subset-2k (~1.6 MB)"),
        ]:
            if skip_existing and dest.exists() and dest.stat().st_size > 1000:
                logger.info("Skipping existing: %s", dest)
            else:
                logger.info("Downloading %s — %s", label, url)
                _download_file(url, dest, session=session)

        # 2. Load metadata and filter by biome
        meta_df = pd.read_csv(raw_metadata, sep="\t", low_memory=False)
        id_col = meta_df.columns[0]
        meta_df = meta_df.rename(columns={id_col: "sample_id"})

        if self.biome_filter:
            filt = self.biome_filter.lower()
            biome_cols = [
                c for c in meta_df.columns
                if any(k in c.lower() for k in ("biome", "empo", "env_biome", "env_feature"))
            ]
            if biome_cols:
                mask = meta_df[biome_cols].apply(
                    lambda col: col.astype(str).str.lower().str.contains(filt, na=False)
                ).any(axis=1)
                meta_df = meta_df[mask]
                logger.info("Biome filter '%s': %d samples kept", self.biome_filter, len(meta_df))

        meta_df = meta_df.head(max_samples)
        selected_ids = set(meta_df["sample_id"].astype(str).tolist())

        # 4. Load BIOM, filter to selected samples, convert to wide TSV
        logger.info("Loading BIOM table (this may take a moment)...")
        table = biom_lib.load_table(str(raw_biom))

        table_ids = set(table.ids(axis="sample"))
        keep_ids = sorted(selected_ids & table_ids)
        if not keep_ids:
            raise IngestionError(
                f"No overlap between selected metadata samples and BIOM table "
                f"({len(selected_ids)} metadata samples vs {len(table_ids)} BIOM samples). "
                "Check that the metadata subset matches the BIOM file.",
                source=str(raw_biom),
            )

        table_filtered = table.filter(keep_ids, axis="sample", inplace=False)
        n_samples_kept, n_features = len(keep_ids), table_filtered.shape[0]  # type: ignore[union-attr]
        logger.info("BIOM filtered: %d samples x %d features", n_samples_kept, n_features)

        wide_df = table_filtered.to_dataframe(dense=True).T  # type: ignore[union-attr]
        wide_df.index.name = "sample_id"
        wide_df = wide_df.reset_index()

        asv_path = out / "asv_table.tsv"
        wide_df.to_csv(asv_path, sep="\t", index=False)
        logger.info("ASV table written: %s (%d samples)", asv_path, len(wide_df))

        # 5. Extract taxonomy from BIOM observation metadata
        # EMP deblur BIOM stores Greengenes lineage as a list under 'taxonomy'
        # e.g. ['k__Bacteria', 'p__Proteobacteria', 'c__Alphaproteobacteria', ...]
        def _parse_lineage(ranks: list) -> dict:
            keys = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
            cleaned = [str(r).split("__", 1)[-1].strip() for r in ranks]
            return {k: (cleaned[i] if i < len(cleaned) else "") for i, k in enumerate(keys)}

        tax_cols = ["feature_id", "kingdom", "phylum", "class", "order", "family", "genus", "species"]
        tax_rows = []
        for _vals, obs_id, obs_meta in table_filtered.iter(axis="observation"):  # type: ignore[union-attr]
            tax_list: list = []
            if obs_meta:
                raw_tax = obs_meta.get("taxonomy", obs_meta.get("Taxon", []))
                if isinstance(raw_tax, list):
                    tax_list = raw_tax
                elif isinstance(raw_tax, str):
                    tax_list = [r.strip() for r in raw_tax.split(";")]
            parsed = _parse_lineage(tax_list)
            parsed["feature_id"] = str(obs_id)
            tax_rows.append(parsed)

        tax_df = pd.DataFrame(tax_rows)[tax_cols] if tax_rows else pd.DataFrame(columns=tax_cols)

        tax_path = out / "taxonomy.tsv"
        tax_df.to_csv(tax_path, sep="\t", index=False)
        logger.info("Taxonomy written: %s (%d features)", tax_path, len(tax_df))

        # 6. Write normalised metadata
        meta_final = meta_df[meta_df["sample_id"].isin(set(wide_df["sample_id"].astype(str)))]
        meta_path  = out / "metadata.tsv"
        meta_final.to_csv(meta_path, sep="\t", index=False)
        logger.info("Metadata written: %s (%d samples)", meta_path, len(meta_final))

        return {
            "asv_table": asv_path,
            "taxonomy":  tax_path,
            "metadata":  meta_path,
        }
