"""Path and identifier boundaries for untrusted jurisdiction-pack inputs."""

from __future__ import annotations

import re
from os import PathLike
from pathlib import Path


SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*", re.ASCII)
FISCAL_YEAR_RE = re.compile(r"[0-9]{4}", re.ASCII)


class PathSafetyError(ValueError):
    """A pack-controlled identifier or path crossed an approved boundary."""


def validate_slug(value: object, *, label: str = "pack slug") -> str:
    if not isinstance(value, str) or SLUG_RE.fullmatch(value) is None:
        raise PathSafetyError(
            f"{label} must contain only lowercase ASCII letters, digits, and "
            "single hyphens"
        )
    return value


def validate_fiscal_year(value: object, *, label: str = "fiscal year") -> str:
    if isinstance(value, bool):
        raise PathSafetyError(f"{label} must be a four-digit year")
    year = str(value)
    if FISCAL_YEAR_RE.fullmatch(year) is None:
        raise PathSafetyError(f"{label} must be a four-digit year")
    return year


def validate_positive_integer(value: object, *, label: str) -> int:
    if isinstance(value, bool):
        raise PathSafetyError(f"{label} must be a positive integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise PathSafetyError(f"{label} must be a positive integer") from exc
    if str(number) != str(value) or number < 1:
        raise PathSafetyError(f"{label} must be a positive integer")
    return number


def resolve_under_root(
    value: str | PathLike[str] | Path,
    *,
    project_root: Path,
    approved_root: Path,
    label: str,
    base: Path | None = None,
    allow_absolute: bool = False,
) -> Path:
    """Return a canonical path proven to remain under ``approved_root``.

    Relative inputs containing ``..`` and drive-relative paths are rejected
    rather than normalized. Existing symlinks are resolved before containment
    is checked. Absolute paths are accepted only for trusted CLI/internal
    callers that opt in, and still must resolve under the approved root.
    """

    project = project_root.resolve(strict=False)
    approved = approved_root.resolve(strict=False)
    try:
        approved.relative_to(project)
    except ValueError as exc:
        raise PathSafetyError(
            f"approved {label} root escapes the project: {approved_root}"
        ) from exc

    try:
        candidate = Path(value)
    except TypeError as exc:
        raise PathSafetyError(f"{label} must be a filesystem path") from exc

    if candidate.drive and not candidate.is_absolute():
        raise PathSafetyError(f"{label} must not be drive-relative: {value!s}")
    if candidate.is_absolute():
        if not allow_absolute:
            raise PathSafetyError(f"{label} must be project-relative: {value!s}")
        target = candidate
    else:
        if ".." in candidate.parts:
            raise PathSafetyError(f"{label} must not contain '..': {value!s}")
        target = (base or project_root) / candidate

    resolved = target.resolve(strict=False)
    try:
        resolved.relative_to(approved)
    except ValueError as exc:
        raise PathSafetyError(
            f"{label} escapes approved root {approved_root}: {value!s}"
        ) from exc
    return resolved
