import asyncio
from typing import cast, Any, Literal
import json
import os

from tavily import AsyncTavilyClient
from langchain_groq import ChatGroq
from langchain_core.runnables import RunnableConfig
from langgraph.graph import START, END, StateGraph
from pydantic import BaseModel, Field

from agent.configuration import Configuration
from agent.state import InputState, OutputState, OverallState
from agent.utils import deduplicate_sources, format_sources, format_all_notes
from agent.prompts import (
    EXTRACTION_PROMPT,
    REFLECTION_PROMPT,
    INFO_PROMPT,
    QUERY_WRITER_PROMPT,
)
from agent.india_queries import get_india_credit_queries, classify_risk_signal

# ── Safety: hard cap on reflection loops to save tokens ──────────────────────
SAFETY_LOOP_LIMIT = 1

# ── LLM: Groq (free tier, 100k tokens/day) ───────────────────────────────────
claude_3_5_sonnet = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0,
)

# ── Search ────────────────────────────────────────────────────────────────────
tavily_async_client = AsyncTavilyClient()


# ── State helper — works with BOTH dict and dataclass ────────────────────────
def _get(state, key, default=None):
    """Works whether LangGraph passes state as dataclass or dict."""
    if hasattr(state, key):
        val = getattr(state, key)
        return val if val is not None else default
    if hasattr(state, "get"):
        return state.get(key, default)
    return default


# ── Pydantic models ───────────────────────────────────────────────────────────
class Queries(BaseModel):
    queries: list[str] = Field(description="List of search queries.")


class ReflectionOutput(BaseModel):
    is_satisfactory: bool = Field(
        description="True if all required fields are well populated, False otherwise"
    )
    missing_fields: list[str] = Field(
        description="List of field names that are missing or incomplete"
    )
    search_queries: list[str] = Field(
        description="If is_satisfactory is False, provide 1-3 targeted search queries"
    )
    reasoning: str = Field(description="Brief explanation of the assessment")


# ── Node 1: generate_queries ──────────────────────────────────────────────────
def generate_queries(state: OverallState, config: RunnableConfig) -> dict[str, Any]:
    """Generate India-specific credit due diligence search queries."""
    configurable = Configuration.from_runnable_config(config)
    max_search_queries = configurable.max_search_queries

    company      = _get(state, "company", "")
    user_notes   = _get(state, "user_notes", "")
    promoter_raw = _get(state, "promoter_names", "")
    sector       = _get(state, "sector", "general") or "general"

    promoter_names = [p.strip() for p in str(promoter_raw).split(",") if p.strip()]

    # India-specific credit queries (the secret weapon)
    india_queries = get_india_credit_queries(
        company_name=company,
        promoter_names=promoter_names,
        sector=sector
    )

    # LLM-generated queries from extraction schema
    structured_llm = claude_3_5_sonnet.with_structured_output(Queries)
    query_instructions = QUERY_WRITER_PROMPT.format(
        company=company,
        info=json.dumps(_get(state, "extraction_schema") or {}, indent=2),
        user_notes=user_notes,
        max_search_queries=min(max_search_queries, 4),
    )
    try:
        llm_result = cast(
            Queries,
            structured_llm.invoke([
                {"role": "system", "content": query_instructions},
                {"role": "user", "content": "Generate search queries for Indian credit due diligence."},
            ]),
        )
        llm_queries = llm_result.queries
    except Exception:
        llm_queries = []

    combined = india_queries[:6] + llm_queries[:2]
    return {"search_queries": combined[:max_search_queries]}


# ── Node 2: research_company ──────────────────────────────────────────────────
async def research_company(
    state: OverallState, config: RunnableConfig
) -> dict[str, Any]:
    """Execute web searches and extract credit risk information."""
    configurable = Configuration.from_runnable_config(config)
    max_search_results = configurable.max_search_results

    search_queries = _get(state, "search_queries") or []

    search_tasks = [
        tavily_async_client.search(
            query,
            max_results=max_search_results,
            include_raw_content=False,
            topic="general",
        )
        for query in search_queries
    ]
    search_docs = await asyncio.gather(*search_tasks)

    deduplicated_search_docs = deduplicate_sources(search_docs)
    source_str = format_sources(
        deduplicated_search_docs, max_tokens_per_source=300, include_raw_content=False
    )

    # Scan for Indian credit risk keywords
    all_text = " ".join([
        doc.get("content", "") + " " + doc.get("title", "")
        for doc in deduplicated_search_docs
    ])
    risk_scan = classify_risk_signal(all_text)

    risk_note = ""
    if risk_scan["signals"]:
        risk_note = f"""

=== CREDIT RISK SIGNALS DETECTED ===
Severity      : {risk_scan['severity']}
Signals found : {', '.join(risk_scan['signals'])}
Five C Impact : {risk_scan['five_c_impact']}
Risk Score    : +{risk_scan['risk_score_add']}/100

IMPORTANT: These signals MUST be prominently mentioned in your analysis.
=====================================
"""

    p = INFO_PROMPT.format(
        info=json.dumps(_get(state, "extraction_schema") or {}, indent=2),
        content=source_str + risk_note,
        company=_get(state, "company", ""),
        user_notes=_get(state, "user_notes", ""),
    )
    result = await claude_3_5_sonnet.ainvoke(p)

    state_update = {"completed_notes": [str(result.content)]}
    if configurable.include_search_results:
        state_update["search_results"] = deduplicated_search_docs

    return state_update


# ── Default schema when user leaves Extraction Schema as {} ──────────────────
DEFAULT_INDIAN_CREDIT_SCHEMA = {
    "title": "IndianCreditResearch",
    "type": "object",
    "properties": {
        "company_overview":            {"type": "string", "description": "Brief company description"},
        "promoter_background":         {"type": "string", "description": "Promoter integrity — ED/CBI/SEBI findings"},
        "promoter_risk_level":         {"type": "string", "description": "LOW / MEDIUM / HIGH / CRITICAL"},
        "litigation_summary":          {"type": "string", "description": "NCLT/DRT/court cases found"},
        "litigation_risk_level":       {"type": "string", "description": "LOW / MEDIUM / HIGH"},
        "npa_default_history":         {"type": "string", "description": "NPA/wilful defaulter/loan recall history"},
        "credit_history_risk_level":   {"type": "string", "description": "LOW / MEDIUM / HIGH / CRITICAL"},
        "regulatory_findings":         {"type": "string", "description": "GST raids, IT surveys, RBI/SEBI actions"},
        "sector_outlook":              {"type": "string", "description": "Sector regulatory and market outlook"},
        "sector_risk_level":           {"type": "string", "description": "LOW / MEDIUM / HIGH"},
        "key_findings":                {"type": "string", "description": "Top 3-5 most important findings"},
        "research_recommendation":     {"type": "string", "description": "PROCEED / CAUTION / HALT"},
        "overall_research_risk_score": {"type": "string", "description": "Risk score 0-100 as a number e.g. 75"},
    },
    "required": ["company_overview", "promoter_risk_level", "research_recommendation", "key_findings"]
}


# ── Node 3: gather_notes_extract_schema ──────────────────────────────────────
def gather_notes_extract_schema(state: OverallState) -> dict[str, Any]:
    """Gather notes and extract into the schema structure."""
    completed_notes   = _get(state, "completed_notes") or []
    extraction_schema = _get(state, "extraction_schema") or {}

    if not extraction_schema:
        extraction_schema = DEFAULT_INDIAN_CREDIT_SCHEMA

    notes = format_all_notes(completed_notes)
    system_prompt = EXTRACTION_PROMPT.format(
        info=json.dumps(extraction_schema, indent=2), notes=notes
    )
    structured_llm = claude_3_5_sonnet.with_structured_output(extraction_schema)
    result = structured_llm.invoke([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Produce a structured output from these notes."},
    ])
    return {"info": result}


# ── Node 4: reflection ────────────────────────────────────────────────────────
def reflection(state: OverallState) -> dict[str, Any]:
    """Reflect on extracted info and decide if more research is needed."""
    extraction_schema      = _get(state, "extraction_schema") or {}
    info                   = _get(state, "info") or {}
    reflection_steps_taken = _get(state, "reflection_steps_taken") or 0

    structured_llm = claude_3_5_sonnet.with_structured_output(ReflectionOutput)
    system_prompt = REFLECTION_PROMPT.format(
        schema=json.dumps(extraction_schema, indent=2),
        info=info,
    )
    result = cast(
        ReflectionOutput,
        structured_llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Produce a structured reflection output."},
        ]),
    )

    print(f"--- Reflection Step {reflection_steps_taken + 1} ---")
    print(f"Satisfactory? {result.is_satisfactory}")

    if result.is_satisfactory:
        return {"is_satisfactory": True}
    else:
        return {
            "is_satisfactory": False,
            "search_queries": result.search_queries,
            "reflection_steps_taken": reflection_steps_taken + 1,
        }


# ── Router ────────────────────────────────────────────────────────────────────
def route_from_reflection(
    state: OverallState, config: RunnableConfig
) -> Literal[END, "research_company"]:  # type: ignore
    configurable = Configuration.from_runnable_config(config)

    is_satisfactory        = _get(state, "is_satisfactory") or False
    reflection_steps_taken = _get(state, "reflection_steps_taken") or 0
    effective_limit        = min(SAFETY_LOOP_LIMIT, configurable.max_reflection_steps)

    if is_satisfactory:
        print(">>> ROUTER: Satisfactory. Ending.")
        return END
    if reflection_steps_taken < effective_limit:
        print(f">>> ROUTER: Retrying ({reflection_steps_taken + 1}/{effective_limit})")
        return "research_company"
    print(">>> ROUTER: Loop limit reached. Forcing END.")
    return END


# ── Graph wiring ──────────────────────────────────────────────────────────────
builder = StateGraph(
    OverallState,
    input=InputState,
    output=OutputState,
    config_schema=Configuration,
)
builder.add_node("gather_notes_extract_schema", gather_notes_extract_schema)
builder.add_node("generate_queries", generate_queries)
builder.add_node("research_company", research_company)
builder.add_node("reflection", reflection)

builder.add_edge(START, "generate_queries")
builder.add_edge("generate_queries", "research_company")
builder.add_edge("research_company", "gather_notes_extract_schema")
builder.add_edge("gather_notes_extract_schema", "reflection")
builder.add_conditional_edges("reflection", route_from_reflection)

graph = builder.compile()