from __future__ import annotations

from copy import deepcopy
from typing import Any


ROLE_ANALYSIS_SCHEMA_NAME = "moredakka_role_analysis"
SYNTHESIS_SCHEMA_NAME = "moredakka_synthesis"
SUPPORTED_SCHEMA_PROFILES = {"software", "generic"}


def _string_array_schema() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    copied = deepcopy(schema)
    copied["type"] = [copied["type"], "null"] if isinstance(copied.get("type"), str) else [*copied.get("type", []), "null"]
    return copied


def _issue_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "detail": {"type": "string"},
            "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
            "evidence": _string_array_schema(),
        },
        "required": ["title", "detail", "severity", "evidence"],
        "additionalProperties": False,
    }


def _candidate_path_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "summary": {"type": "string"},
            "tradeoffs": _string_array_schema(),
        },
        "required": ["name", "summary", "tradeoffs"],
        "additionalProperties": False,
    }


def _action_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "why": {"type": "string"},
            "artifacts": _string_array_schema(),
            "commands": _string_array_schema(),
            "acceptance": _string_array_schema(),
            "effort": {"type": "string", "enum": ["small", "medium", "large"]},
            "priority": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        "required": ["title", "why", "artifacts", "commands", "acceptance", "effort", "priority"],
        "additionalProperties": False,
    }


def _software_step_schema() -> dict[str, Any]:
    schema = _action_schema()
    schema["properties"]["files"] = _string_array_schema()
    schema["required"] = ["title", "why", "files", "commands", "acceptance", "effort", "priority"]
    del schema["properties"]["artifacts"]
    return schema


def _validation_check_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "kind": {"type": "string", "enum": ["unit", "integration", "e2e", "manual", "static", "reasoning", "simulation", "checklist"]},
            "command": {"type": "string"},
            "purpose": {"type": "string"},
        },
        "required": ["name", "kind", "command", "purpose"],
        "additionalProperties": False,
    }


def _risk_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "impact": {"type": "string"},
            "likelihood": {"type": "string", "enum": ["low", "medium", "high"]},
            "mitigation": {"type": "string"},
        },
        "required": ["name", "impact", "likelihood", "mitigation"],
        "additionalProperties": False,
    }


def _edit_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "file": {"type": "string"},
            "change_type": {"type": "string", "enum": ["edit", "create", "delete", "rename"]},
            "reason": {"type": "string"},
            "summary": {"type": "string"},
        },
        "required": ["file", "change_type", "reason", "summary"],
        "additionalProperties": False,
    }


def _commit_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "files": _string_array_schema(),
        },
        "required": ["title", "summary", "files"],
        "additionalProperties": False,
    }


def _disagreement_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "topic": {"type": "string"},
            "positions": _string_array_schema(),
            "recommended_resolution": {"type": "string"},
        },
        "required": ["topic", "positions", "recommended_resolution"],
        "additionalProperties": False,
    }


def _status_ledger_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "done": _string_array_schema(),
            "remaining": _string_array_schema(),
            "blocked": _string_array_schema(),
            "next": _string_array_schema(),
        },
        "required": ["done", "remaining", "blocked", "next"],
        "additionalProperties": False,
    }


def _intent_card_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "goal": {"type": "string"},
            "selected_path": {"type": "string"},
            "open_questions": _string_array_schema(),
        },
        "required": ["goal", "selected_path", "open_questions"],
        "additionalProperties": False,
    }


def _common_role_properties(action_key: str, validation_key: str, action_schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": {"type": "string"},
        "focus": {"type": "string"},
        "one_sentence_take": {"type": "string"},
        "observations": _string_array_schema(),
        "top_problems": {"type": "array", "items": _issue_schema()},
        "candidate_paths": {"type": "array", "items": _candidate_path_schema()},
        action_key: {"type": "array", "items": action_schema},
        validation_key: {"type": "array", "items": _validation_check_schema()},
        "risks": {"type": "array", "items": _risk_schema()},
        "assumptions": _string_array_schema(),
        "questions": _string_array_schema(),
        "stop_conditions": _string_array_schema(),
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    }


def role_analysis_schema(profile: str = "software") -> dict[str, Any]:
    if profile == "software":
        properties = _common_role_properties("recommended_steps", "tests", _software_step_schema())
        properties["edits"] = {"type": "array", "items": _edit_schema()}
        required = list(properties.keys())
    elif profile == "generic":
        properties = _common_role_properties("recommended_actions", "validation_checks", _action_schema())
        required = list(properties.keys())
    else:
        raise KeyError(profile)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _common_synthesis_properties(action_key: str, validation_key: str, action_schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "inferred_objective": {"type": "string"},
        "one_sentence_take": {"type": "string"},
        "selected_path": _candidate_path_schema(),
        "top_problems": {"type": "array", "items": _issue_schema()},
        action_key: {"type": "array", "items": action_schema},
        validation_key: {"type": "array", "items": _validation_check_schema()},
        "major_risks": {"type": "array", "items": _risk_schema()},
        "disagreements": {"type": "array", "items": _disagreement_schema()},
        "stop_conditions": _string_array_schema(),
        "open_questions": _string_array_schema(),
        "operator_summary": _nullable({"type": "string"}),
        "handoff_paragraph": _nullable({"type": "string"}),
        "status_ledger": _nullable(_status_ledger_schema()),
        "intent_card": _nullable(_intent_card_schema()),
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "confidence_rationale": {"type": "string"},
    }


def synthesis_schema(profile: str = "software") -> dict[str, Any]:
    if profile == "software":
        properties = _common_synthesis_properties("next_actions", "tests", _software_step_schema())
        properties["commit_plan"] = {"type": "array", "items": _commit_schema()}
        properties["edit_targets"] = {"type": "array", "items": _edit_schema()}
        required = list(properties.keys())
    elif profile == "generic":
        properties = _common_synthesis_properties("next_actions", "validation_checks", _action_schema())
        required = list(properties.keys())
    else:
        raise KeyError(profile)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def minimal_shape_ok(payload: dict[str, Any], *, synthesis: bool = False, profile: str = "software") -> bool:
    schema = synthesis_schema(profile) if synthesis else role_analysis_schema(profile)
    required = schema["required"]
    return isinstance(payload, dict) and all(key in payload for key in required)


def schema_copy(name: str, profile: str = "software") -> dict[str, Any]:
    if name == ROLE_ANALYSIS_SCHEMA_NAME:
        return deepcopy(role_analysis_schema(profile))
    if name == SYNTHESIS_SCHEMA_NAME:
        return deepcopy(synthesis_schema(profile))
    raise KeyError(name)


def schema_name_for_profile(name: str, profile: str) -> str:
    if profile not in SUPPORTED_SCHEMA_PROFILES:
        raise KeyError(profile)
    return f"{name}_{profile}"
