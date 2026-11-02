from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ValidationError

from .config import AppConfig


ExampleFormat = Literal["yaml", "env"]
FieldSource = Callable[[], set[str]]


def registered_fields(*names: str) -> FieldSource:
    """Build a reusable field source for formats without a Pydantic model."""
    fields = frozenset(names)
    return lambda: set(fields)


def model_field_paths(model: type[BaseModel], prefix: str = "") -> set[str]:
    """Return public leaf fields as dotted paths, preserving their nesting."""
    paths: set[str] = set()
    for name, definition in model.model_fields.items():
        path = f"{prefix}.{name}" if prefix else name
        annotation = definition.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            paths.update(model_field_paths(annotation, path))
        else:
            paths.add(path)
    return paths


def mapping_field_paths(value: Mapping[str, Any], prefix: str = "") -> set[str]:
    paths: set[str] = set()
    for name, child in value.items():
        path = f"{prefix}.{name}" if prefix else name
        if isinstance(child, Mapping) and child:
            paths.update(mapping_field_paths(child, path))
        else:
            paths.add(path)
    return paths


@dataclass(frozen=True, slots=True)
class ExampleSpec:
    relative_path: Path
    format: ExampleFormat
    field_source: FieldSource
    model: type[BaseModel] | None = None
    excluded_fields: Mapping[str, str] = field(default_factory=dict)
    secret_placeholders: Mapping[str, frozenset[str]] = field(default_factory=dict)
    compare_model_defaults: bool = False


@dataclass(frozen=True, slots=True)
class ExampleReport:
    relative_path: Path
    missing: tuple[str, ...] = ()
    extra: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()
    default_mismatches: tuple[str, ...] = ()
    unsafe_secrets: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not any((
            self.missing, self.extra, self.forbidden, self.default_mismatches,
            self.unsafe_secrets, self.errors,
        ))

    def lines(self) -> list[str]:
        lines = [f"{self.relative_path}:"]
        for label, values in (
            ("missing fields", self.missing),
            ("extra or misplaced fields", self.extra),
            ("excluded fields must not be published", self.forbidden),
            ("values differ from model defaults", self.default_mismatches),
            ("secret fields need a safe placeholder", self.unsafe_secrets),
            ("errors", self.errors),
        ):
            if values:
                lines.append(f"  {label}: {', '.join(values)}")
        return lines


# There are currently no AppConfig fields excluded from the public YAML example.
# Any future entry must include a reason and will be rejected if published by mistake.
CONFIG_EXAMPLE_EXCLUSIONS: Mapping[str, str] = {}


REGISTERED_EXAMPLES = (
    ExampleSpec(
        relative_path=Path("config.example.yaml"),
        format="yaml",
        field_source=lambda: model_field_paths(AppConfig),
        model=AppConfig,
        excluded_fields=CONFIG_EXAMPLE_EXCLUSIONS,
        compare_model_defaults=True,
    ),
)


def _load_yaml(path: Path) -> Mapping[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, Mapping):
        raise ValueError("root must be an object")
    return loaded


def _load_env(path: Path) -> Mapping[str, Any]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError("environment entry must contain =")
        name, value = line.split("=", 1)
        if not name.strip():
            raise ValueError("environment entry needs a name")
        values[name.strip()] = value.strip()
    return values


LOADERS: Mapping[ExampleFormat, Callable[[Path], Mapping[str, Any]]] = {
    "yaml": _load_yaml,
    "env": _load_env,
}


def _path_value(value: Mapping[str, Any], dotted: str) -> Any:
    current: Any = value
    for name in dotted.split("."):
        if not isinstance(current, Mapping) or name not in current:
            return None
        current = current[name]
    return current


def check_example(root: Path, spec: ExampleSpec) -> ExampleReport:
    path = root / spec.relative_path
    if not path.is_file():
        return ExampleReport(spec.relative_path, errors=("file does not exist",))
    try:
        raw = LOADERS[spec.format](path)
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        return ExampleReport(
            spec.relative_path,
            errors=(f"could not parse {spec.format} ({type(exc).__name__})",),
        )

    expected_all = spec.field_source()
    excluded = set(spec.excluded_fields)
    expected = expected_all - excluded
    actual = mapping_field_paths(raw)
    forbidden = actual & excluded
    extra = actual - expected - forbidden
    default_mismatches: set[str] = set()
    errors: list[str] = []

    if spec.model is not None:
        try:
            parsed = spec.model.model_validate(raw).model_dump(mode="json")
        except ValidationError as exc:
            locations = sorted({
                ".".join(str(part) for part in item["loc"])
                for item in exc.errors(include_input=False)
            })
            errors.append(f"model validation failed at {', '.join(locations)}")
        else:
            if spec.compare_model_defaults:
                defaults = spec.model().model_dump(mode="json")
                default_mismatches = {
                    name for name in expected
                    if _path_value(parsed, name) != _path_value(defaults, name)
                }

    unsafe_secrets = {
        name for name, placeholders in spec.secret_placeholders.items()
        if name in actual and str(_path_value(raw, name)) not in placeholders
    }
    return ExampleReport(
        relative_path=spec.relative_path,
        missing=tuple(sorted(expected - actual)),
        extra=tuple(sorted(extra)),
        forbidden=tuple(sorted(forbidden)),
        default_mismatches=tuple(sorted(default_mismatches)),
        unsafe_secrets=tuple(sorted(unsafe_secrets)),
        errors=tuple(errors),
    )


def check_registered_examples(root: Path) -> tuple[ExampleReport, ...]:
    return tuple(check_example(root, spec) for spec in REGISTERED_EXAMPLES)
