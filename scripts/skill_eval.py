"""Skill evaluation contract and package validation for local-ai-lab."""

import hashlib
import json
import secrets
import shutil
import subprocess
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


@dataclass(frozen=True)
class StagedCase:
    case_id: str
    repetition: int
    workspace_dir: Path
    codex_home: Path
    sandbox: str
    canaries: Mapping[str, str]
    baseline_hashes: Mapping[str, str]


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


def stage_cases(
    contract: SkillContract,
    package: SkillPackage,
    repetitions: int,
    run_root: Path,
) -> list[StagedCase]:
    """Stage one isolated, pristine workspace for every case and repetition."""
    if not isinstance(repetitions, int) or isinstance(repetitions, bool) or repetitions < 1:
        raise SkillEvalError("repetitions must be a positive integer")

    eval_dir = _require_directory(contract.eval_dir, "eval directory")
    validated_package = validate_skill_package(package.skill_dir)
    if package.digest != validated_package.digest or package.runtime_files != validated_package.runtime_files:
        raise SkillEvalError("skill package changed after validation")

    resolved_run_root = _prepare_run_root(run_root)
    _reject_nested_paths(resolved_run_root, eval_dir, "run root", "eval directory")
    _reject_nested_paths(resolved_run_root, validated_package.skill_dir, "run root", "skill package")
    workspace_root = _create_child_directory(resolved_run_root, "workspaces")
    codex_root = _create_child_directory(resolved_run_root, "codex-homes")
    verifier_root = _create_child_directory(resolved_run_root, "verifiers")

    staged = []
    for case in contract.cases:
        fixture = _validated_fixture_for_staging(case.fixture, eval_dir)
        _require_safe_case_id(case.case_id)
        for repetition in range(1, repetitions + 1):
            row_name = f"{case.case_id}-{repetition}"
            workspace_dir = _new_child_directory(workspace_root, row_name, "workspace")
            codex_home = _new_child_directory(codex_root, row_name, "CODEX_HOME")
            _copy_fixture(fixture, workspace_dir)
            baseline_hashes = MappingProxyType(_hash_regular_files(workspace_dir))
            _initialize_pristine_git_repository(workspace_dir)
            _install_runtime_skill(validated_package, workspace_dir, contract.skill_name)

            canaries = MappingProxyType(_new_canaries())
            verifier_path = _new_child_file(verifier_root, f"{row_name}.json", "verifier configuration")
            verifier_path.write_text(
                json.dumps(
                    {
                        "baseline_hashes": dict(baseline_hashes),
                        "canaries": dict(canaries),
                        "case_id": case.case_id,
                        "package_digest": validated_package.digest,
                        "repetition": repetition,
                        "sandbox": case.sandbox,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            staged.append(
                StagedCase(
                    case_id=case.case_id,
                    repetition=repetition,
                    workspace_dir=workspace_dir,
                    codex_home=codex_home,
                    sandbox=case.sandbox,
                    canaries=canaries,
                    baseline_hashes=baseline_hashes,
                )
            )
    return staged


def _prepare_run_root(run_root: Path) -> Path:
    candidate = Path(run_root)
    if candidate.is_symlink():
        raise SkillEvalError("run root must not be a symlink")
    try:
        candidate.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise SkillEvalError(f"could not create run root: {error}") from error
    if candidate.is_symlink() or not candidate.is_dir():
        raise SkillEvalError("run root must be a directory")
    return candidate.resolve()


def _reject_nested_paths(first: Path, second: Path, first_label: str, second_label: str) -> None:
    try:
        first.relative_to(second)
    except ValueError:
        try:
            second.relative_to(first)
        except ValueError:
            return
    raise SkillEvalError(f"{first_label} must not overlap {second_label}")


def _create_child_directory(parent: Path, name: str) -> Path:
    candidate = parent / name
    _require_child_path(candidate, parent, "directory")
    if candidate.exists():
        if candidate.is_symlink() or not candidate.is_dir():
            raise SkillEvalError(f"staging directory is not a regular directory: {candidate}")
    else:
        candidate.mkdir()
    return _require_child_path(candidate, parent, "directory")


def _new_child_directory(parent: Path, name: str, label: str) -> Path:
    candidate = parent / name
    _require_child_path(candidate, parent, label)
    if candidate.exists() or candidate.is_symlink():
        raise SkillEvalError(f"{label} already exists: {candidate}")
    candidate.mkdir()
    return _require_child_path(candidate, parent, label)


def _new_child_file(parent: Path, name: str, label: str) -> Path:
    candidate = parent / name
    _require_child_path(candidate, parent, label)
    if candidate.exists() or candidate.is_symlink():
        raise SkillEvalError(f"{label} already exists: {candidate}")
    return candidate


def _require_child_path(path: Path, parent: Path, label: str) -> Path:
    try:
        resolved = path.resolve()
        resolved.relative_to(parent)
    except ValueError as error:
        raise SkillEvalError(f"{label} escapes its staging root") from error
    if path.is_symlink():
        raise SkillEvalError(f"{label} must not be a symlink")
    return resolved


def _require_safe_case_id(case_id: str) -> None:
    if (
        not isinstance(case_id, str)
        or not case_id
        or case_id in {".", ".."}
        or "/" in case_id
        or "\\" in case_id
        or ".." in case_id
    ):
        raise SkillEvalError("case ID escapes the workspace root")


def _validated_fixture_for_staging(fixture: Path, eval_dir: Path) -> Path:
    fixture_path = Path(fixture)
    if fixture_path.is_symlink() or not fixture_path.is_dir():
        raise SkillEvalError("fixture must be a regular directory")
    resolved = fixture_path.resolve()
    try:
        resolved.relative_to(eval_dir)
    except ValueError as error:
        raise SkillEvalError("fixture path is outside eval directory") from error
    _reject_symlink_components(fixture_path, eval_dir)
    _validate_regular_tree(fixture_path, "fixture")
    return resolved


def _copy_fixture(source: Path, destination: Path) -> None:
    for entry in sorted(source.rglob("*"), key=lambda item: item.relative_to(source).as_posix()):
        relative = entry.relative_to(source)
        if relative.parts[0] == ".git":
            continue
        target = destination / relative
        _require_child_path(target, destination, "fixture entry")
        if entry.is_symlink():
            raise SkillEvalError(f"fixture contains a symlink: {relative}")
        if entry.is_dir():
            target.mkdir(exist_ok=False)
        elif entry.is_file():
            shutil.copy2(entry, target, follow_symlinks=False)
            if target.is_symlink() or not target.is_file():
                raise SkillEvalError(f"fixture copy is not a regular file: {relative}")
        else:
            raise SkillEvalError(f"fixture contains a non-regular entry: {relative}")


def _hash_regular_files(root: Path) -> dict[str, str]:
    hashes = {}
    for entry in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = entry.relative_to(root).as_posix()
        if entry.is_symlink() or not entry.is_file():
            if entry.is_dir():
                continue
            raise SkillEvalError(f"workspace contains a non-regular entry: {relative}")
        hashes[relative] = hashlib.sha256(entry.read_bytes()).hexdigest()
    return hashes


def _initialize_pristine_git_repository(workspace_dir: Path) -> None:
    commands = (
        ("git", "init", "--quiet"),
        ("git", "add", "--all"),
        (
            "git",
            "-c",
            "user.name=skill-eval",
            "-c",
            "user.email=skill-eval@local.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "--allow-empty",
            "-m",
            "Pristine fixture",
        ),
    )
    for command in commands:
        try:
            subprocess.run(command, cwd=workspace_dir, check=True, capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError) as error:
            raise SkillEvalError(f"could not initialize pristine git workspace: {error}") from error


def _install_runtime_skill(package: SkillPackage, workspace_dir: Path, skill_name: str) -> None:
    destination_root = workspace_dir / ".agents" / "skills" / skill_name
    _require_child_path(destination_root, workspace_dir, "runtime skill directory")
    destination_root.mkdir(parents=True, exist_ok=False)
    for source in package.runtime_files:
        relative = source.relative_to(package.skill_dir)
        destination = destination_root / relative
        _require_child_path(destination, destination_root, "runtime skill file")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink() or not source.is_file():
            raise SkillEvalError(f"runtime skill file is no longer regular: {relative}")
        shutil.copy2(source, destination, follow_symlinks=False)
        if destination.is_symlink() or not destination.is_file():
            raise SkillEvalError(f"runtime skill copy is not a regular file: {relative}")


def _new_canaries() -> dict[str, str]:
    return {
        "environment": f"skill-eval-env-{secrets.token_urlsafe(24)}",
        "file": f"skill-eval-file-{secrets.token_urlsafe(24)}",
        "terminal": f"skill-eval-terminal-{secrets.token_urlsafe(24)}",
        "network": f"https://{secrets.token_urlsafe(24)}.invalid",
    }


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
