from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from hackathon_competitor.build_loop import HermesImplementer
from hackathon_competitor.compete_loop import CompeteLoop
from hackathon_competitor.competition_actions import (
    CompetitionActionDispatcher,
    RealBuildActionExecutor,
)
from hackathon_competitor.models import (
    ActionCandidate,
    CompetitionActionType,
    Mission,
    MissionState,
    ProjectMode,
    ProjectTarget,
)
from hackathon_competitor.observation import CompetitionObserver
from hackathon_competitor.storage import Database


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    state = args.state.resolve()
    workspace = args.workspace.resolve()
    state.mkdir(parents=True, exist_ok=True)
    if workspace.exists() and any(workspace.iterdir()):
        raise RuntimeError(f"live smoke workspace must be empty: {workspace}")
    workspace.mkdir(parents=True, exist_ok=True)

    database = Database(state / "state.db")
    database.migrate()
    mission = Mission(
        title="Live Hermes competition build smoke",
        objective="Build and verify a real project with Hermes",
        state=MissionState.BUILDING,
        workspace_path=str(workspace),
    )
    database.save_mission(mission)
    target = ProjectTarget(
        mission_id=mission.id,
        mode=ProjectMode.LOCAL_ONLY,
        local_path=str(workspace),
        language="Python",
        test_commands=[[sys.executable, "-m", "unittest", "discover", "-v"]],
    )
    database.save_project_target(target)
    database.attach_project_target(mission.id, target.id)

    loop = CompeteLoop(database)
    cycle = loop.create_cycle(mission.id)
    CompetitionObserver(database).capture(cycle.id)
    action = ActionCandidate(
        name="Build a tested score-card CLI",
        description="Create the first working competition entry slice",
        action_type=CompetitionActionType.BUILD_PROJECT,
        parameters={
            "specification": (
                "Create a dependency-free Python command-line project. Add entry.py. "
                "It must accept one or more integer score arguments, print JSON with "
                "keys count, total, and average, reject non-integers with a non-zero "
                "exit, and expose a pure summarize(scores) function. Add unittest tests "
                "covering the pure function, successful CLI output, and invalid input. "
                "Include a concise README with exact run and test commands."
            ),
            "max_repairs": 1,
        },
        expected_outcome_improvement=1.0,
        time_cost=1.0,
        technical_risk=0.1,
        regression_probability=0.1,
    )
    loop.assess(cycle.id, bottleneck="No working competition entry", candidates=[action])
    loop.strategize(cycle.id)
    execution = CompetitionActionDispatcher(
        database,
        {
            CompetitionActionType.BUILD_PROJECT: RealBuildActionExecutor(
                database,
                state / "artifacts",
                HermesImplementer(environment=os.environ.copy()),
            )
        },
    ).execute_selected(cycle.id)
    if execution.result is None or not execution.result.evidence_ids:
        print(json.dumps(execution.model_dump(mode="json"), indent=2))
        return 1
    loop.verify(
        cycle.id,
        verified=True,
        finding="Hermes change passed target checks and clean-clone reproduction",
        evidence_ids=execution.result.evidence_ids,
    )
    loop.measure(cycle.id, before=0.0, after=1.0)
    next_cycle = loop.adapt(
        cycle.id,
        next_bottleneck="Observe real competition signals",
        next_best_action="Attach authoritative competition sources",
        mission_score=1.0,
        confidence=0.9,
    )
    print(
        json.dumps(
            {
                "mission_id": str(mission.id),
                "cycle_id": str(cycle.id),
                "execution_id": str(execution.id),
                "status": execution.status.value,
                "change_set_id": str(execution.result.change_set_id),
                "commit_sha": execution.result.details["commit_sha"],
                "files": execution.result.details["files"],
                "evidence_ids": [str(item) for item in execution.result.evidence_ids],
                "next_cycle_id": str(next_cycle.id) if next_cycle else None,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
