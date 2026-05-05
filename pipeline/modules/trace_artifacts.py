"""Helpers for merging and writing persisted pipeline trace artifacts."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass
class TraceArchive:
    """Merged stage and function events for one traced PMID."""

    pmid: str
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    function_events: list[dict[str, Any]] = field(default_factory=list)
    function_counts_by_stage: dict[str, int] = field(default_factory=dict)
    function_counts_by_name: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_sources(cls, pmid: str, sources: Iterable[Path]) -> "TraceArchive":
        archive = cls(pmid=str(pmid))
        target_pmid = str(pmid).strip()

        for path in sources:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except Exception:
                        continue
                    archive.add_event(event, target_pmid=target_pmid)
        return archive

    def add_event(self, event: dict[str, Any], *, target_pmid: str | None = None) -> None:
        event_type = event.get("type")
        if event_type in {"fn_call", "fn_return"}:
            event_pmid = str(event.get("pmid") or "").strip()
            if target_pmid is not None and event_pmid and event_pmid != target_pmid:
                return
            self.function_events.append(event)
            stage = str(event.get("stage_id") or "unscoped")
            name = ".".join(
                part
                for part in [
                    str(event.get("module") or "").strip(),
                    str(event.get("function") or "").strip(),
                ]
                if part
            ) or "unknown"
            self.function_counts_by_stage[stage] = (
                self.function_counts_by_stage.get(stage, 0) + 1
            )
            self.function_counts_by_name[name] = self.function_counts_by_name.get(name, 0) + 1
            return

        node_id = event.get("node_id")
        if not node_id:
            return
        # Last-write-wins for repeated node IDs, matching the original viewer contract.
        self.nodes[node_id] = event

    def write(self, output_path: Path, *, generated_at: float | None = None) -> Path:
        out_path = Path(output_path)
        function_trace_path = out_path.with_name(f"{out_path.stem}_functions.jsonl")
        if self.function_events:
            function_trace_path.parent.mkdir(parents=True, exist_ok=True)
            with open(function_trace_path, "w", encoding="utf-8") as f:
                for event in self.function_events:
                    f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

        payload = {
            "pmid": self.pmid,
            "generated_at": time.time() if generated_at is None else generated_at,
            "node_count": len(self.nodes),
            "nodes": self.nodes,
            "function_event_count": len(self.function_events),
            "function_trace_path": str(function_trace_path) if self.function_events else "",
            "function_counts_by_stage": dict(
                sorted(self.function_counts_by_stage.items(), key=lambda item: (-item[1], item[0]))
            ),
            "function_counts_by_name": dict(
                sorted(self.function_counts_by_name.items(), key=lambda item: (-item[1], item[0]))[:200]
            ),
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
        return out_path
