from __future__ import annotations

import json
from pathlib import Path

from .serialization import bundle_to_dict


class LocalBundlePublisher:
    def __init__(self, outdir: Path) -> None:
        self.outdir = Path(outdir)

    def publish(self, bundle) -> None:
        self.outdir.mkdir(parents=True, exist_ok=True)
        published_path = self.outdir / "published_bundle.json"
        published_path.write_text(
            json.dumps(bundle_to_dict(bundle), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
