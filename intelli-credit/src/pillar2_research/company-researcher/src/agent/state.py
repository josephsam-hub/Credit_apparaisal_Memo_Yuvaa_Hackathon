"""state.py — Modified for Intelli-Credit (Indian credit appraisal)"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(kw_only=True)
class InputState:
    """Input fields shown in LangGraph Studio form."""
    company: str
    extraction_schema: dict = field(default_factory=dict)
    user_notes: str = ""
    # ── ADDED: Indian credit fields ──────────────────────────────────────────
    promoter_names: str = ""           # e.g. "Neeraj Singal"
    sector: str = ""                   # e.g. "steel manufacturing"
    loan_amount_requested_cr: str = "" # e.g. "500"


@dataclass(kw_only=True)
class OutputState:
    """Fields returned in the final output."""
    info: dict = field(default_factory=dict)


@dataclass(kw_only=True)
class OverallState:
    """Full internal state used across all nodes."""
    # ── Core inputs ───────────────────────────────────────────────────────────
    company: str = ""
    extraction_schema: dict = field(default_factory=dict)
    user_notes: str = ""
    promoter_names: str = ""
    sector: str = ""
    loan_amount_requested_cr: str = ""

    # ── Research pipeline ─────────────────────────────────────────────────────
    search_queries: list[str] = field(default_factory=list)
    search_results: list[dict] = field(default_factory=list)
    completed_notes: list[str] = field(default_factory=list)
    info: dict = field(default_factory=dict)

    # ── Reflection loop ───────────────────────────────────────────────────────
    is_satisfactory: bool = False
    reflection_steps_taken: int = 0