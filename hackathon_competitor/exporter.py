from __future__ import annotations

import json
import zipfile
from pathlib import Path
from uuid import UUID

from .storage import Database


def export_mission_bundle(database: Database, mission_id: UUID, output: Path) -> Path:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = database.export_mission(mission_id)
    manifest: list[dict[str, object]] = []
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mission.json", json.dumps(payload, indent=2, sort_keys=True))
        for artifact in database.list_artifacts(mission_id):
            source = Path(artifact.path)
            item = {
                "id": str(artifact.id),
                "kind": artifact.kind,
                "content_hash": artifact.content_hash,
                "stale": artifact.stale,
                "included": source.is_file(),
            }
            manifest.append(item)
            if source.is_file():
                archive.write(source, f"artifacts/{artifact.id}-{source.name}")
        archive.writestr("artifact-manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    return output
