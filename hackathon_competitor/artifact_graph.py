from __future__ import annotations

from uuid import UUID

from .models import Artifact
from .storage import Database


class ArtifactGraph:
    def __init__(self, database: Database):
        self.database = database

    def link(self, parent: Artifact, child: Artifact, dependency_type: str) -> None:
        if parent.mission_id != child.mission_id:
            raise ValueError("artifact dependencies cannot cross missions")
        self.database.add_artifact_dependency(parent.id, child.id, dependency_type)

    def upstream_changed(self, artifact_id: UUID) -> list[Artifact]:
        return self.database.mark_artifact_descendants_stale(artifact_id)
