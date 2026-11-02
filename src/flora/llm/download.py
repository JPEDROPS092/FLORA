"""Download GGUF models from Hugging Face into the models directory.

Only ``https://<endpoint>/<owner>/<repo>/resolve/<revision>/<file>.gguf`` is ever requested:
repo and file names are validated, files land in the models directory via a ``.part`` file
and are renamed atomically when complete. One job runs at a time.
"""

from __future__ import annotations

import os
import re
import shutil
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from flora.llm.client import LlmError

_REPO = re.compile(r"^[A-Za-z0-9][\w.-]{0,95}/[A-Za-z0-9][\w.-]{0,95}$")
_FILE = re.compile(r"^[A-Za-z0-9][\w.+-]{0,200}\.gguf$", re.IGNORECASE)
_REV = re.compile(r"^[\w.-]{1,64}$")
_CHUNK = 1024 * 256
MAX_BYTES = int(os.environ.get("FLORA_MAX_MODEL_GB", "24")) * 1024**3


def endpoint() -> str:
    return os.environ.get("FLORA_HF_ENDPOINT", "https://huggingface.co").rstrip("/")


@dataclass
class PullJob:
    id: str
    repo: str
    file: str
    status: str = "queued"  # queued | downloading | done | error | cancelled
    bytes_done: int = 0
    bytes_total: int = 0
    error: str = ""
    started: float = field(default_factory=time.time)
    cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    def public(self) -> dict[str, Any]:
        pct = round(100 * self.bytes_done / self.bytes_total, 1) if self.bytes_total else 0.0
        return {
            "id": self.id, "repo": self.repo, "file": self.file, "status": self.status,
            "bytes_done": self.bytes_done, "bytes_total": self.bytes_total, "percent": pct,
            "error": self.error, "elapsed_s": round(time.time() - self.started, 1),
        }


_jobs: dict[str, PullJob] = {}
_lock = threading.Lock()


def validate(repo: str, file: str, revision: str = "main") -> None:
    if not isinstance(repo, str) or not _REPO.match(repo):
        raise LlmError("repo must look like owner/name.")
    if not isinstance(file, str) or not _FILE.match(file):
        raise LlmError("file must be a plain .gguf file name (no folders).")
    if not _REV.match(revision):
        raise LlmError("Invalid revision.")


def start(models_dir: Path, repo: str, file: str, revision: str = "main") -> PullJob:
    validate(repo, file, revision)
    with _lock:
        if any(j.status in {"queued", "downloading"} for j in _jobs.values()):
            raise LlmError("Another download is already running.")
        job = PullJob(id=uuid.uuid4().hex[:12], repo=repo, file=file)
        _jobs[job.id] = job
    threading.Thread(target=_run, args=(job, Path(models_dir), revision), daemon=True).start()
    return job


def get(job_id: str) -> PullJob:
    job = _jobs.get(job_id)
    if job is None:
        raise LlmError("Unknown download job.")
    return job


def cancel(job_id: str) -> PullJob:
    job = get(job_id)
    job.cancel.set()
    return job


def _run(job: PullJob, models_dir: Path, revision: str) -> None:
    url = f"{endpoint()}/{job.repo}/resolve/{revision}/{job.file}"
    headers = {"User-Agent": "flora-model-puller"}
    token = os.environ.get("HF_TOKEN")  # optional: gated or private repos
    if token:
        headers["Authorization"] = f"Bearer {token}"
    target = models_dir / job.file
    part = models_dir / f"{job.file}.part"
    try:
        models_dir.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise LlmError(f"{job.file} already exists in the models directory.")
        job.status = "downloading"
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as resp:  # noqa: S310
            job.bytes_total = int(resp.headers.get("Content-Length") or 0)
            if job.bytes_total > MAX_BYTES:
                raise LlmError(f"File is larger than the {MAX_BYTES // 1024**3} GB limit.")
            if job.bytes_total and shutil.disk_usage(models_dir).free < job.bytes_total * 1.05:
                raise LlmError("Not enough free disk space.")
            with part.open("wb") as fh:
                while chunk := resp.read(_CHUNK):
                    if job.cancel.is_set():
                        job.status = "cancelled"
                        return
                    fh.write(chunk)
                    job.bytes_done += len(chunk)
                    if job.bytes_done > MAX_BYTES:
                        raise LlmError("Download exceeded the size limit.")
        if job.bytes_total and job.bytes_done != job.bytes_total:
            raise LlmError("Download ended early (size mismatch).")
        with part.open("rb") as fh:
            if fh.read(4) != b"GGUF":
                raise LlmError("Downloaded file is not a GGUF model.")
        os.replace(part, target)
        job.status = "done"
    except urllib.error.HTTPError as exc:
        hint = " (gated model? set HF_TOKEN on the server)" if exc.code in {401, 403} else ""
        job.status, job.error = "error", f"HTTP {exc.code} from the model host{hint}"
    except (urllib.error.URLError, TimeoutError, OSError, LlmError) as exc:
        job.status, job.error = "error", str(getattr(exc, "reason", exc))
    finally:
        if job.status != "done":
            part.unlink(missing_ok=True)
