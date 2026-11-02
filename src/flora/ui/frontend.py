"""Frontend asset resolution for the FLORA Angular web interface."""

from __future__ import annotations

from dataclasses import dataclass
from mimetypes import guess_type
from pathlib import Path

PACKAGE_DIR = Path(__file__).parent
STATIC_ROOT = PACKAGE_DIR / "static"
SPA_BUILD_DIR = STATIC_ROOT / "app"
# Output of ``scripts/build_frontend.sh``; only a fallback for ``SPA_BUILD_DIR``.
FRONT_DIST_DIR = PACKAGE_DIR.parent / "front" / "dist"


def spa_root_dir() -> Path:
    """Return the directory that contains the built SPA assets.

    The ``frontend/angular`` build in ``SPA_BUILD_DIR`` wins; the
    ``flora/front/dist`` build is used only when that one is absent.
    """
    for candidate in (SPA_BUILD_DIR / "browser", SPA_BUILD_DIR, FRONT_DIST_DIR):
        if (candidate / "index.html").exists():
            return candidate
    return SPA_BUILD_DIR


def spa_index_path() -> Path:
    """Return the active SPA entrypoint path."""
    return spa_root_dir() / "index.html"


@dataclass(frozen=True)
class FrontendAsset:
    """Resolved static frontend asset ready to be served over HTTP."""

    path: Path
    content_type: str
    binary: bool


class FrontendNotBuiltError(RuntimeError):
    """Raised when the Angular SPA has not been built yet."""


def has_built_frontend() -> bool:
    """Return ``True`` when a compiled SPA is available on disk."""
    return spa_index_path().exists()


def frontend_mode() -> str:
    """Return the active frontend mode used by the HTTP server."""
    return "angular-spa" if has_built_frontend() else "missing-build"


def load_index_html() -> str:
    """Load the Angular SPA entrypoint HTML."""
    if not has_built_frontend():
        raise FrontendNotBuiltError(
            "Angular UI build not found. Run `cd frontend/angular && npm run build`."
        )
    return spa_index_path().read_text(encoding="utf-8")


def resolve_frontend_asset(request_path: str) -> FrontendAsset | None:
    """Resolve a frontend static asset under the compiled SPA directory."""
    if not has_built_frontend():
        return None

    normalized = request_path.lstrip("/")
    if not normalized:
        return None

    build_root = spa_root_dir().resolve()
    asset_path = (build_root / normalized).resolve()

    if build_root not in asset_path.parents:
        return None
    if not asset_path.exists() or not asset_path.is_file():
        return None

    content_type, _ = guess_type(asset_path.name)
    return FrontendAsset(
        path=asset_path,
        content_type=content_type or "application/octet-stream",
        binary=not (content_type or "").startswith("text/"),
    )


def should_serve_spa_index(request_path: str) -> bool:
    """Return ``True`` when the request should fall back to SPA index.html."""
    if not has_built_frontend():
        return False

    normalized = request_path.strip()
    if not normalized or normalized == "/":
        return True

    leaf = normalized.rsplit("/", maxsplit=1)[-1]
    return "." not in leaf
