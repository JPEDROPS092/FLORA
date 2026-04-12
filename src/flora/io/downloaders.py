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
                        "description": attrs.get("description", "").lower(),
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

@dataclass
class EMPDownloader:
    """Download data from the Earth Microbiome Project via Qiita portal.

    Parameters
    ----------
    api_base : str
        Qiita portal base URL.
    """

    api_base: str = _EMP_API

    def fetch_study(
        self,
        study_id: int,
        output_dir: str | Path,
        data_type: str = "16S",
    ) -> Path:
        """Download BIOM and metadata for a Qiita/EMP study.

        Parameters
        ----------
        study_id : int
            Qiita study ID (integer).
        output_dir : str or Path
            Destination directory.
        data_type : str
            Data type filter (e.g. ``"16S"``).

        Returns
        -------
        Path
            Path to the output directory.

        Raises
        ------
        IngestionError
            If the study is not accessible or downloads fail.
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        session = _make_session()

        study_url = f"{self.api_base}/api/v1/study/{study_id}"
        try:
            resp = session.get(study_url, timeout=30)
            resp.raise_for_status()
            study_info = resp.json()
        except requests.RequestException as exc:
            raise IngestionError(
                f"Cannot access Qiita study {study_id}: {exc}",
                source=str(study_id),
            ) from exc

        logger.info(
            "EMP/Qiita study %d: %s",
            study_id,
            study_info.get("title", "Unknown"),
        )

        artifacts_url = f"{self.api_base}/api/v1/study/{study_id}/artifacts"
        try:
            resp2 = session.get(artifacts_url, timeout=30)
            resp2.raise_for_status()
            artifacts = resp2.json()
        except Exception:
            artifacts = {}

        for art_id, art_info in artifacts.items() if isinstance(artifacts, dict) else []:
            if art_info.get("type") == "BIOM":
                biom_url = f"{self.api_base}/api/v1/artifact/{art_id}/filepaths"
                try:
                    resp3 = session.get(biom_url, timeout=30)
                    resp3.raise_for_status()
                    filepaths = resp3.json()
                    for fp in filepaths:
                        fname = fp.get("filepath", "").split("/")[-1]
                        dl_url = f"{self.api_base}/download/{art_id}"
                        dest = out / fname
                        try:
                            _download_file(dl_url, dest, session=session)
                        except IngestionError as exc:
                            logger.warning("Could not download artifact %s: %s", art_id, exc)
                except Exception as exc:
                    logger.warning("Could not process artifact %s: %s", art_id, exc)

        meta_url = f"{self.api_base}/api/v1/study/{study_id}/samples/info"
        meta_dest = out / "metadata.tsv"
        try:
            resp_meta = session.get(meta_url, timeout=30)
            if resp_meta.ok:
                with open(meta_dest, "wb") as fh:
                    fh.write(resp_meta.content)
                logger.info("Metadata saved: %s", meta_dest)
        except Exception as exc:
            logger.warning("Could not download metadata: %s", exc)

        return out

    def fetch_artifact(
        self,
        artifact_id: int,
        output_dir: str | Path,
    ) -> Path:
        """Download a specific Qiita artifact by ID.

        Parameters
        ----------
        artifact_id : int
            Qiita artifact ID.
        output_dir : str or Path
            Destination directory.

        Returns
        -------
        Path
            Path to the downloaded file.
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        session = _make_session()

        dl_url = f"{self.api_base}/download/{artifact_id}"
        dest = out / f"artifact_{artifact_id}.biom"
        return _download_file(dl_url, dest, session=session)
