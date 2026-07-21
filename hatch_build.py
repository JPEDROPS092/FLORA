"""Hatch build hook for FLORA.

Optionally builds the Angular frontend before creating the wheel.
Requires Node.js and npm if the frontend dist/ directory doesn't exist.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from hatchling.builders.plugin.interface import BuilderHookInterface


class HatchBuildHook(BuilderHookInterface):
    """Build hook that optionally compiles the Angular frontend."""

    def initialize(self, version: str, build_data: dict) -> None:
        root = Path(self.root)
        front_dir = root / "src" / "flora" / "front"
        dist_dir = front_dir / "dist"
        script = root / "scripts" / "build_frontend.sh"

        if dist_dir.is_dir() and any(dist_dir.iterdir()):
            print(f"[flora] Frontend dist found at {dist_dir}")
            return

        if not script.exists():
            print(
                f"[flora] WARNING: Frontend not built and build script not found.\n"
                f"  Run: ./scripts/build_frontend.sh\n"
                f"  The UI will fall back to the embedded HTML interface."
            )
            return

        node = shutil.which("node")
        npm = shutil.which("npm")
        if not node or not npm:
            print(
                "[flora] WARNING: Node.js/npm not found. Skipping frontend build.\n"
                "  The UI will fall back to the embedded HTML interface.\n"
                "  To build the frontend, install Node.js and run:\n"
                "    ./scripts/build_frontend.sh"
            )
            return

        print("[flora] Building Angular frontend...")
        try:
            subprocess.run(
                [str(script)],
                cwd=str(root),
                check=True,
                capture_output=True,
                text=True,
            )
            print("[flora] Frontend built successfully.")
        except subprocess.CalledProcessError as exc:
            print(
                f"[flora] WARNING: Frontend build failed:\n{exc.stderr}\n"
                "  The UI will fall back to the embedded HTML interface."
            )
