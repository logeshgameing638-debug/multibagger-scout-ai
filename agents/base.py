"""Agent base: every agent returns an AgentResult and its run is recorded.

Agents are deterministic Python. No LLM is required. An agent that could not
complete says so (status=failed/partial) instead of fabricating output.
"""
from __future__ import annotations

import json
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from database.connection import session_scope
from database.models import AgentOutput, AgentRun


@dataclass
class AgentResult:
    agent_name: str
    status: str  # success / partial / failed
    data: dict[str, Any] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    error: str | None = None

    def finish(self) -> "AgentResult":
        self.finished_at = datetime.now(timezone.utc)
        return self

    def to_json(self) -> str:
        return json.dumps(
            {
                "agent_name": self.agent_name,
                "status": self.status,
                "data": self.data,
                "missing": self.missing,
                "warnings": self.warnings,
                "sources": self.sources,
                "started_at": str(self.started_at),
                "finished_at": str(self.finished_at),
                "error": self.error,
            },
            default=str,
        )


def validate_output(result: AgentResult, required_keys: list[str]) -> tuple[bool, str]:
    """Validate an agent's output structure before it is trusted downstream."""
    errors = []
    for key in required_keys:
        if key not in result.data:
            errors.append(f"missing required output key '{key}'")
    if result.status not in {"success", "partial", "failed"}:
        errors.append(f"invalid status '{result.status}'")
    return (not errors), "; ".join(errors)


def run_recorded(
    agent_name: str,
    work: Callable[[], AgentResult],
    company_id: int | None = None,
    input_summary: str = "",
    required_keys: list[str] | None = None,
) -> AgentResult:
    """Run an agent function, persist the run and validate the output."""
    run = AgentRun(agent_name=agent_name, status="success", input_summary=input_summary)
    try:
        result = work()
    except Exception as exc:
        result = AgentResult(
            agent_name=agent_name,
            status="failed",
            error=f"{exc}",
            warnings=[traceback.format_exc(limit=3)],
        ).finish()
    if result.finished_at is None:
        result.finish()
    run.status = result.status
    run.started_at = result.started_at
    run.finished_at = result.finished_at
    run.error = result.error

    valid, validation_errors = validate_output(result, required_keys or [])
    if not valid:
        run.status = "partial"
        result.status = "partial"
        result.warnings.append(f"output validation: {validation_errors}")

    with session_scope() as session:
        session.add(run)
        session.flush()
        session.add(
            AgentOutput(
                run_id=run.id,
                company_id=company_id,
                output_json=result.to_json(),
                valid=valid,
                validation_errors=validation_errors,
            )
        )
        result.data["_run_id"] = run.id
    return result
