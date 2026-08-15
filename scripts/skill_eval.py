"""Skill evaluation contract and package validation for local-ai-lab."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Optional, Tuple

import yaml


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "skills" / "cases.schema.json"
APPROVED_CATEGORIES = (
    "direct_activation",
    "implicit_activation",
    "negative_activation",
)
APPROVED_SANDBOXES = ("read-only", "workspace-write", "danger-full-access")
DETERMINISTIC_ASSERTION_TYPES = (
    "contains",
    "not-contains",
    "equals",
    "not-equals",
    "regex",
    "not-regex",
    "starts-with",
)


class SkillEvalError(ValueError):
    """Raised when a skill evaluation input cannot safely be used."""


@dataclass(frozen=True)
class ExpectedEffects:
    skill_used: bool
    output: Tuple[Mapping[str, str], ...]
    files: Mapping[str, Tuple[str, ...]]
    forbidden: Mapping[str, Any]


@dataclass(frozen=True)
class SkillCase:
    case_id: str
    category: str
    prompt: str
    fixture: Path
    sandbox: str
    expected: ExpectedEffects
    rubric: str


@dataclass(frozen=True)
class SkillContract:
    schema_version: int
    skill_name: str
    purpose: str
    cases: Tuple[SkillCase, ...]
    eval_dir: Path


@dataclass(frozen=True)
class SkillPackage:
    skill_dir: Path
    runtime_files: Tuple[Path, ...]
    digest: str


def load_skill_contract(skill_dir: Path, eval_dir: Optional[Path] = None) -> SkillContract:
    """Load and validate the version-1 cases contract before any inference."""
    resolved_skill_dir = _require_directory(skill_dir, "skill directory")
    resolved_eval_dir = _resolve_eval_dir(resolved_skill_dir, eval_dir)
    cases_path = resolved_eval_dir / "cases.yaml"
    if cases_path.is_symlink():
        raise SkillEvalError("cases.yaml must not be a symlink")
    if not cases_path.is_file():
        raise SkillEvalError(f"missing contract file: {cases_path}")

    try:
        raw_contract = yaml.safe_load(cases_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise SkillEvalError(f"could not read cases.yaml: {error}") from error

    contract = _require_mapping(raw_contract, "contract")
    _validate_against_v1_schema(contract)
    _reject_unknown_keys(contract, {"schema_version", "skill", "cases"}, "contract")
    if not isinstance(contract.get("schema_version"), int) or isinstance(contract.get("schema_version"), bool) or contract.get("schema_version") != 1:
        raise SkillEvalError("schema_version must be 1")

    skill = _require_mapping(contract.get("skill"), "skill")
    _reject_unknown_keys(skill, {"name", "purpose"}, "skill")
    skill_name = _require_text(skill.get("name"), "skill.name")
    if skill_name != resolved_skill_dir.name:
        raise SkillEvalError("skill.name must match the skill directory name")
    purpose = _require_text(skill.get("purpose"), "skill.purpose")

    raw_cases = contract.get("cases")
    if not isinstance(raw_cases, list):
        raise SkillEvalError("cases must be a list")
    cases = tuple(_parse_case(case, index, resolved_eval_dir) for index, case in enumerate(raw_cases))
    _validate_case_coverage(cases)

    return SkillContract(1, skill_name, purpose, cases, resolved_eval_dir)


def validate_skill_package(skill_dir: Path) -> SkillPackage:
    """Validate a publishable skill package and return its canonical digest."""
    resolved_skill_dir = _require_directory(skill_dir, "skill directory")
    skill_file = resolved_skill_dir / "SKILL.md"
    if skill_file.is_symlink() or not skill_file.is_file():
        raise SkillEvalError("skill package must contain a regular SKILL.md file")

    runtime_files = []
    for entry in sorted(resolved_skill_dir.rglob("*"), key=lambda item: item.relative_to(resolved_skill_dir).as_posix()):
        relative_name = entry.relative_to(resolved_skill_dir).as_posix()
        if entry.is_symlink():
            raise SkillEvalError(f"skill package contains a symlink: {relative_name}")
        if entry.name in {".skill-evals", ".local-ai-lab"}:
            raise SkillEvalError("skill package must not contain private evaluation data")
        if entry.is_dir():
            continue
        if not entry.is_file():
            raise SkillEvalError(f"skill package contains a non-regular entry: {relative_name}")
        runtime_files.append(entry)

    return SkillPackage(
        skill_dir=resolved_skill_dir,
        runtime_files=tuple(runtime_files),
        digest=_package_digest(resolved_skill_dir, runtime_files),
    )


def _resolve_eval_dir(skill_dir: Path, eval_dir: Optional[Path]) -> Path:
    if eval_dir is None:
        repository_root = _find_repository_root(skill_dir)
        eval_dir = repository_root / ".skill-evals" / skill_dir.name
    return _require_directory(eval_dir, "eval directory")


def _find_repository_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    raise SkillEvalError("could not find a git root for the default eval directory")


def _require_directory(path: Path, label: str) -> Path:
    path = Path(path)
    if path.is_symlink():
        raise SkillEvalError(f"{label} must not be a symlink")
    if not path.is_dir():
        raise SkillEvalError(f"{label} must be a directory: {path}")
    return path.resolve()


def _parse_case(raw_case: Any, index: int, eval_dir: Path) -> SkillCase:
    case = _require_mapping(raw_case, f"cases[{index}]")
    _reject_unknown_keys(
        case,
        {"id", "category", "prompt", "fixture", "sandbox", "expected", "rubric"},
        f"cases[{index}]",
    )
    case_id = _require_text(case.get("id"), f"cases[{index}].id")
    category = _require_text(case.get("category"), f"cases[{index}].category")
    if category not in APPROVED_CATEGORIES:
        raise SkillEvalError(f"unsupported category: {category}")
    prompt = _require_text(case.get("prompt"), f"cases[{index}].prompt")
    fixture = _fixture_path(_require_text(case.get("fixture"), f"cases[{index}].fixture"), eval_dir)
    sandbox = _require_text(case.get("sandbox"), f"cases[{index}].sandbox")
    if sandbox not in APPROVED_SANDBOXES:
        raise SkillEvalError(f"unsupported sandbox: {sandbox}")
    expected = _parse_expected(case.get("expected"), index)
    rubric = _require_text(case.get("rubric"), f"cases[{index}].rubric")
    return SkillCase(case_id, category, prompt, fixture, sandbox, expected, rubric)


def _fixture_path(reference: str, eval_dir: Path) -> Path:
    reference_path = Path(reference)
    if reference_path.is_absolute() or ".." in reference_path.parts:
        raise SkillEvalError("fixture path is outside eval directory")
    candidate = eval_dir / reference
    resolved = candidate.resolve()
    try:
        resolved.relative_to(eval_dir)
    except ValueError as error:
        raise SkillEvalError("fixture path is outside eval directory") from error
    if candidate.is_symlink():
        raise SkillEvalError("fixture path must not be a symlink")
    _reject_symlink_components(candidate, eval_dir)
    if not candidate.is_dir():
        raise SkillEvalError(f"fixture must be a directory: {reference}")
    _validate_regular_tree(candidate, "fixture")
    return resolved


def _reject_symlink_components(path: Path, root: Path) -> None:
    current = root
    for component in path.relative_to(root).parts:
        current = current / component
        if current.is_symlink():
            raise SkillEvalError(f"fixture path contains a symlink: {current.relative_to(root)}")


def _validate_regular_tree(root: Path, label: str) -> None:
    for entry in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if entry.is_symlink():
            raise SkillEvalError(f"{label} contains a symlink: {entry.relative_to(root)}")
        if entry.is_dir() or entry.is_file():
            continue
        raise SkillEvalError(f"{label} contains a non-regular entry: {entry.relative_to(root)}")


def _parse_expected(raw_expected: Any, index: int) -> ExpectedEffects:
    expected = _require_mapping(raw_expected, f"cases[{index}].expected")
    _reject_unknown_keys(expected, {"skill_used", "output", "files", "forbidden"}, f"cases[{index}].expected")
    skill_used = expected.get("skill_used")
    if not isinstance(skill_used, bool):
        raise SkillEvalError(f"cases[{index}].expected.skill_used must be a boolean")

    raw_output = expected.get("output")
    if not isinstance(raw_output, list) or not raw_output:
        raise SkillEvalError(f"cases[{index}].expected.output must be a nonempty list")
    output = tuple(_parse_output_assertion(assertion, index, assertion_index) for assertion_index, assertion in enumerate(raw_output))

    files = _require_mapping(expected.get("files"), f"cases[{index}].expected.files")
    _reject_unknown_keys(files, {"unchanged", "created"}, f"cases[{index}].expected.files")
    parsed_files = MappingProxyType({
        "unchanged": _string_list(files.get("unchanged"), f"cases[{index}].expected.files.unchanged"),
        "created": _string_list(files.get("created"), f"cases[{index}].expected.files.created"),
    })

    forbidden = _require_mapping(expected.get("forbidden"), f"cases[{index}].expected.forbidden")
    _reject_unknown_keys(forbidden, {"command_patterns", "path_patterns", "network"}, f"cases[{index}].expected.forbidden")
    network = forbidden.get("network")
    if not isinstance(network, bool):
        raise SkillEvalError(f"cases[{index}].expected.forbidden.network must be a boolean")
    parsed_forbidden = MappingProxyType({
        "command_patterns": _string_list(forbidden.get("command_patterns"), f"cases[{index}].expected.forbidden.command_patterns"),
        "path_patterns": _string_list(forbidden.get("path_patterns"), f"cases[{index}].expected.forbidden.path_patterns"),
        "network": network,
    })
    return ExpectedEffects(skill_used, output, parsed_files, parsed_forbidden)


def _parse_output_assertion(raw_assertion: Any, case_index: int, assertion_index: int) -> Mapping[str, str]:
    label = f"cases[{case_index}].expected.output[{assertion_index}]"
    assertion = _require_mapping(raw_assertion, label)
    _reject_unknown_keys(assertion, {"type", "value"}, label)
    assertion_type = _require_text(assertion.get("type"), f"{label}.type")
    if assertion_type not in DETERMINISTIC_ASSERTION_TYPES:
        raise SkillEvalError(f"unsupported deterministic assertion type: {assertion_type}")
    return MappingProxyType({"type": assertion_type, "value": _require_text(assertion.get("value"), f"{label}.value")})


def _validate_case_coverage(cases: Tuple[SkillCase, ...]) -> None:
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise SkillEvalError("case IDs must be unique; duplicate ID found")
    for category in APPROVED_CATEGORIES:
        if sum(case.category == category for case in cases) < 2:
            raise SkillEvalError(f"category {category} requires at least two cases")


def _package_digest(skill_dir: Path, runtime_files: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in runtime_files:
        digest.update(path.relative_to(skill_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _validate_against_v1_schema(value: Mapping[str, Any]) -> None:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SkillEvalError(f"could not load v1 contract schema: {error}") from error
    error = _schema_error(value, schema, schema, "contract")
    if error:
        raise SkillEvalError(f"contract does not satisfy v1 schema: {error}")


def _schema_error(value: Any, schema: Mapping[str, Any], root_schema: Mapping[str, Any], label: str) -> Optional[str]:
    reference = schema.get("$ref")
    if reference is not None:
        if not isinstance(reference, str) or not reference.startswith("#/"):
            return f"{label} has an unsupported schema reference"
        target: Any = root_schema
        for component in reference[2:].split("/"):
            if not isinstance(target, dict) or component not in target:
                return f"{label} references a missing schema definition"
            target = target[component]
        if not isinstance(target, dict):
            return f"{label} references an invalid schema definition"
        return _schema_error(value, target, root_schema, label)

    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(value, dict):
            return f"{label} must be an object"
        for required in schema.get("required", []):
            if required not in value:
                return f"{label}.{required} is required"
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    return f"{label}.{key} is not allowed"
        for key, child_schema in properties.items():
            if key in value:
                child_error = _schema_error(value[key], child_schema, root_schema, f"{label}.{key}")
                if child_error:
                    return child_error
    elif expected_type == "array":
        if not isinstance(value, list):
            return f"{label} must be an array"
        if len(value) < schema.get("minItems", 0):
            return f"{label} must have at least {schema['minItems']} entries"
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(value):
                child_error = _schema_error(item, item_schema, root_schema, f"{label}[{index}]")
                if child_error:
                    return child_error
    elif expected_type == "string":
        if not isinstance(value, str):
            return f"{label} must be a string"
        if len(value) < schema.get("minLength", 0):
            return f"{label} must not be empty"
    elif expected_type == "boolean" and not isinstance(value, bool):
        return f"{label} must be a boolean"
    elif expected_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
        return f"{label} must be an integer"

    if "const" in schema and value != schema["const"]:
        return f"{label} must equal {schema['const']!r}"
    if "enum" in schema and value not in schema["enum"]:
        if label.endswith(".type"):
            return f"{label} has an unsupported assertion type"
        return f"{label} is not an allowed value"
    return None


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise SkillEvalError(f"{label} must be a mapping")
    return value


def _reject_unknown_keys(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise SkillEvalError(f"{label} has unknown field(s): {', '.join(unknown)}")


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SkillEvalError(f"{label} must be nonempty text")
    return value


def _string_list(value: Any, label: str) -> Tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise SkillEvalError(f"{label} must be a list of nonempty strings")
    return tuple(value)
