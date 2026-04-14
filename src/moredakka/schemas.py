from __future__ import annotations

from copy import deepcopy
from typing import Any


ROLE_ANALYSIS_SCHEMA_NAME = "moredakka_role_analysis"
SYNTHESIS_SCHEMA_NAME = "moredakka_synthesis"


def _string_array_schema() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


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


def _step_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "why": {"type": "string"},
            "files": _string_array_schema(),
            "commands": _string_array_schema(),
            "acceptance": _string_array_schema(),
            "effort": {"type": "string", "enum": ["small", "medium", "large"]},
            "priority": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        "required": ["title", "why", "files", "commands", "acceptance", "effort", "priority"],
        "additionalProperties": False,
    }


def _test_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "kind": {"type": "string", "enum": ["unit", "integration", "e2e", "manual", "static"]},
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


def role_analysis_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "role": {"type": "string"},
            "focus": {"type": "string"},
            "one_sentence_take": {"type": "string"},
            "top_problems": {"type": "array", "items": _issue_schema()},
            "candidate_paths": {"type": "array", "items": _candidate_path_schema()},
            "recommended_steps": {"type": "array", "items": _step_schema()},
            "tests": {"type": "array", "items": _test_schema()},
            "risks": {"type": "array", "items": _risk_schema()},
            "edits": {"type": "array", "items": _edit_schema()},
            "assumptions": _string_array_schema(),
            "questions": _string_array_schema(),
            "stop_conditions": _string_array_schema(),
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": [
            "role",
            "focus",
            "one_sentence_take",
            "top_problems",
            "candidate_paths",
            "recommended_steps",
            "tests",
            "risks",
            "edits",
            "assumptions",
            "questions",
            "stop_conditions",
            "confidence",
        ],
        "additionalProperties": False,
    }


def synthesis_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "inferred_objective": {"type": "string"},
            "one_sentence_take": {"type": "string"},
            "selected_path": _candidate_path_schema(),
            "top_problems": {"type": "array", "items": _issue_schema()},
            "next_actions": {"type": "array", "items": _step_schema()},
            "commit_plan": {"type": "array", "items": _commit_schema()},
            "tests": {"type": "array", "items": _test_schema()},
            "edit_targets": {"type": "array", "items": _edit_schema()},
            "major_risks": {"type": "array", "items": _risk_schema()},
            "disagreements": {"type": "array", "items": _disagreement_schema()},
            "stop_conditions": _string_array_schema(),
            "open_questions": _string_array_schema(),
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "confidence_rationale": {"type": "string"},
        },
        "required": [
            "inferred_objective",
            "one_sentence_take",
            "selected_path",
            "top_problems",
            "next_actions",
            "commit_plan",
            "tests",
            "edit_targets",
            "major_risks",
            "disagreements",
            "stop_conditions",
            "open_questions",
            "confidence",
            "confidence_rationale",
        ],
        "additionalProperties": False,
    }


def minimal_shape_ok(payload: dict[str, Any], *, synthesis: bool = False) -> bool:
    schema = synthesis_schema() if synthesis else role_analysis_schema()
    required = schema["required"]
    return isinstance(payload, dict) and all(key in payload for key in required)


def schema_copy(name: str) -> dict[str, Any]:
    if name == ROLE_ANALYSIS_SCHEMA_NAME:
        return deepcopy(role_analysis_schema())
    if name == SYNTHESIS_SCHEMA_NAME:
        return deepcopy(synthesis_schema())
    raise KeyError(name)
