"""Offline validation for vendor-neutral municipal evidence handoffs.

Models may discover and classify candidate sources. This module never invokes a
model, fetches a URL, edits canonical data, or grants publication status.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator

from .models import canonical_sha256


ROOT = Path(__file__).resolve().parents[1]
JOB_SCHEMA_PATH = (
    ROOT / "national" / "schemas" / "municipal-evidence-handoff-job.schema.json"
)
CANDIDATE_SCHEMA_PATH = (
    ROOT / "national" / "schemas" / "municipal-evidence-candidate.schema.json"
)
TRUSTED_JOB_MANIFEST_SCHEMA_PATH = (
    ROOT
    / "national"
    / "schemas"
    / "municipal-evidence-trusted-job-manifest.schema.json"
)
TRUSTED_JOB_MANIFEST_PATH = ROOT / "handoffs" / "trusted-job-manifest.json"
PREFETCHED_PACKET_SCHEMA_PATH = (
    ROOT / "national" / "schemas" / "prefetched-source-packet.schema.json"
)
CANONICAL_GOVERNMENT_DIRECTORY_SCHEMA_PATH = (
    ROOT / "national" / "schemas" / "canonical-government-directory.schema.json"
)
MAX_JSON_BYTES = 1_000_000
MAX_JSON_DEPTH = 64

_SECRET_PATTERNS = (
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bxai-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{25,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}=*\b", re.IGNORECASE),
    re.compile(r"\bBasic\s+[A-Za-z0-9+/]{16,}={0,2}\b", re.IGNORECASE),
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
    ),
    re.compile(
        r"\b(?:password|passwd|pwd|secret|token)\s*[:=]\s*[^\s,;]{8,}",
        re.IGNORECASE,
    ),
    re.compile(r"[?&](?:sig|signature|token)=[A-Za-z0-9%._~+/-]{16,}", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
_LOCAL_PATH_PATTERN = re.compile(
    r"(?:"
    r"\b[A-Za-z]:[\\/]"
    r"|file://"
    r"|\\\\[^\\\s]+\\"
    r"|(?<![A-Za-z0-9])~[\\/]"
    r"|(?<![A-Za-z0-9:/])/"
    r"(?:Users|home|tmp|var|etc|opt|root|private|Volumes|mnt|srv|workspace)/"
    r")",
    re.IGNORECASE,
)
_EMAIL_ADDRESS_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+-])"
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    r"(?![A-Za-z0-9._%+-])"
)
_PHONE_LIKE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:\+?1[\s.-]?)?"
    r"(?:\([2-9][0-9]{2}\)[\s.-]?|[2-9][0-9]{2}[\s.-]?)"
    r"[2-9][0-9]{2}[\s.-]?[0-9]{4}"
    r"(?:\s*(?:x|ext\.?)\s*[0-9]{1,6})?"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_CANADIAN_SIN_CANDIDATE_PATTERN = re.compile(
    r"(?<![0-9])(?:[0-9][ -]?){8}[0-9](?![0-9])"
)


class ModelHandoffError(ValueError):
    """A handoff document failed a closed, deterministic validation gate."""


def _contains_valid_canadian_sin(text: str) -> bool:
    """Return true only for a nine-digit candidate with a valid Luhn checksum."""

    for match in _CANADIAN_SIN_CANDIDATE_PATTERN.finditer(text):
        digits = [int(character) for character in match.group() if character.isdigit()]
        total = 0
        for index, digit in enumerate(digits):
            value = digit * 2 if index % 2 else digit
            total += value // 10 + value % 10
        if total % 10 == 0:
            return True
    return False


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ModelHandoffError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ModelHandoffError(f"non-finite JSON number is forbidden: {value}")


def _reject_float(value: str) -> None:
    raise ModelHandoffError(f"floating-point JSON number is forbidden: {value}")


def _check_depth(value: Any, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise ModelHandoffError("strict JSON nesting limit exceeded")
    if isinstance(value, Mapping):
        for item in value.values():
            _check_depth(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _check_depth(item, depth + 1)


def parse_strict_json(payload: str | bytes) -> Any:
    """Parse JSON without duplicate keys, floats, non-finite values, or deep trees."""

    if isinstance(payload, bytes):
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ModelHandoffError("handoff JSON must be UTF-8") from exc
    elif isinstance(payload, str):
        text = payload
    else:
        raise ModelHandoffError("handoff JSON must be text or bytes")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
            parse_float=_reject_float,
        )
    except ModelHandoffError:
        raise
    except RecursionError as exc:
        raise ModelHandoffError("strict JSON nesting limit exceeded") from exc
    except (json.JSONDecodeError, UnicodeError, ValueError) as exc:
        raise ModelHandoffError("invalid strict JSON") from exc
    try:
        _check_depth(value)
    except RecursionError as exc:
        raise ModelHandoffError("strict JSON nesting limit exceeded") from exc
    return value


def load_strict_json(path: str | Path) -> Any:
    supplied = Path(path)
    if supplied.is_symlink():
        raise ModelHandoffError(f"symlinked handoff file is forbidden: {supplied}")
    try:
        stat = supplied.stat()
    except OSError as exc:
        raise ModelHandoffError(f"cannot read handoff file: {supplied}") from exc
    if not supplied.is_file():
        raise ModelHandoffError(f"handoff path is not a regular file: {supplied}")
    if stat.st_size < 2 or stat.st_size > MAX_JSON_BYTES:
        raise ModelHandoffError(
            f"handoff JSON byte length must be 2..{MAX_JSON_BYTES}: {supplied}"
        )
    try:
        return parse_strict_json(supplied.read_bytes())
    except OSError as exc:
        raise ModelHandoffError(f"cannot read handoff file: {supplied}") from exc


def _load_schema(path: Path) -> dict[str, Any]:
    value = load_strict_json(path)
    if not isinstance(value, dict):
        raise ModelHandoffError(f"schema root must be an object: {path}")
    try:
        Draft202012Validator.check_schema(value)
    except Exception as exc:  # jsonschema exposes several schema error subclasses
        raise ModelHandoffError(f"invalid checked-in schema: {path.name}") from exc
    return value


def _validate_schema(
    value: Mapping[str, Any],
    schema_path: Path,
    *,
    label: str,
) -> None:
    schema = _load_schema(schema_path)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path) or "<root>"
        raise ModelHandoffError(
            f"{label} schema rejected {location}: {first.message}"
        )


def _trusted_relative_path(value: str, *, label: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or "\\" in value or ".." in relative.parts:
        raise ModelHandoffError(f"{label} must be a safe repository-relative path")
    resolved_root = ROOT.resolve()
    resolved = (ROOT / relative).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ModelHandoffError(f"{label} escapes the repository") from exc
    if (ROOT / relative).is_symlink():
        raise ModelHandoffError(f"{label} cannot point to a symlink")
    return resolved


def _normalize_jurisdiction(value: Any, *, label: str) -> str:
    jurisdiction = str(value).upper()
    if re.fullmatch(r"(?:AB|BC|MB|NB|NL|NS|NT|NU|ON|PE|QC|SK|YT)", jurisdiction):
        return f"CA-{jurisdiction}"
    if re.fullmatch(
        r"CA-(?:AB|BC|MB|NB|NL|NS|NT|NU|ON|PE|QC|SK|YT)",
        jurisdiction,
    ):
        return jurisdiction
    raise ModelHandoffError(f"{label} is not a Canadian province/territory")


def _load_trusted_job_manifest() -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
]:
    manifest = load_strict_json(TRUSTED_JOB_MANIFEST_PATH)
    if not isinstance(manifest, dict):
        raise ModelHandoffError("trusted job manifest root must be an object")
    _validate_schema(
        manifest,
        TRUSTED_JOB_MANIFEST_SCHEMA_PATH,
        label="trusted job manifest",
    )

    prompt_entry = manifest["prompt"]
    prompt_path = _trusted_relative_path(
        prompt_entry["path"],
        label="trusted job manifest prompt.path",
    )
    try:
        prompt_digest = hashlib.sha256(prompt_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ModelHandoffError("cannot read the trusted handoff prompt") from exc
    if prompt_digest != prompt_entry["utf8Sha256"]:
        raise ModelHandoffError("trusted handoff prompt digest does not match")

    schema_entry = manifest["candidateSchema"]
    candidate_schema_path = _trusted_relative_path(
        schema_entry["path"],
        label="trusted job manifest candidateSchema.path",
    )
    candidate_schema = _load_schema(candidate_schema_path)
    if canonical_sha256(candidate_schema) != schema_entry["canonicalSha256"]:
        raise ModelHandoffError("trusted candidate schema digest does not match")

    directories: dict[str, dict[str, Any]] = {}
    directory_digests: set[str] = set()
    for directory_entry in manifest["targetDirectories"]:
        relative_path = directory_entry["path"]
        if relative_path in directories:
            raise ModelHandoffError(
                "trusted job manifest contains a duplicate target directory path"
            )
        if directory_entry["canonicalSha256"] in directory_digests:
            raise ModelHandoffError(
                "trusted job manifest contains a duplicate target directory digest"
            )
        directory_path = _trusted_relative_path(
            relative_path,
            label="trusted job manifest targetDirectories.path",
        )
        directory = load_strict_json(directory_path)
        if not isinstance(directory, dict):
            raise ModelHandoffError("trusted target directory root must be an object")
        directory_schema_version = directory.get("schemaVersion")
        if directory_schema_version == "auditback-canonical-government-directory-3.0.0":
            _validate_schema(
                directory,
                CANONICAL_GOVERNMENT_DIRECTORY_SCHEMA_PATH,
                label="trusted canonical government directory",
            )
        elif directory_schema_version != "ontario-municipal-history-index-2.0.0":
            raise ModelHandoffError(
                "trusted target directory uses an unsupported schema version"
            )
        observed_jurisdiction = _normalize_jurisdiction(
            directory.get("jurisdiction"),
            label="trusted target directory jurisdiction",
        )
        if (
            directory.get("schemaVersion") != directory_entry["schemaVersion"]
            or observed_jurisdiction != directory_entry["jurisdiction"]
        ):
            raise ModelHandoffError("trusted target directory identity does not match")
        if canonical_sha256(directory) != directory_entry["canonicalSha256"]:
            raise ModelHandoffError("trusted target directory digest does not match")
        directories[relative_path] = directory
        directory_digests.add(directory_entry["canonicalSha256"])

    job_ids: set[str] = set()
    job_paths: set[str] = set()
    job_hashes: set[str] = set()
    authority_identities: dict[str, tuple[str, str, tuple[str, ...]]] = {}
    for entry in manifest["jobs"]:
        if entry["jobId"] in job_ids:
            raise ModelHandoffError("trusted job manifest contains a duplicate jobId")
        if entry["path"] in job_paths:
            raise ModelHandoffError("trusted job manifest contains a duplicate job path")
        if entry["jobCanonicalSha256"] in job_hashes:
            raise ModelHandoffError("trusted job manifest contains a duplicate job digest")
        if entry["targetDirectoryPath"] not in directories:
            raise ModelHandoffError(
                "trusted job references an unlisted target directory path"
            )
        job_ids.add(entry["jobId"])
        job_paths.add(entry["path"])
        job_hashes.add(entry["jobCanonicalSha256"])

        checked_path = _trusted_relative_path(
            entry["path"],
            label=f"trusted job {entry['jobId']} path",
        )
        checked_job = load_strict_json(checked_path)
        if not isinstance(checked_job, dict):
            raise ModelHandoffError(
                f"trusted job {entry['jobId']} root must be an object"
            )
        _validate_schema(checked_job, JOB_SCHEMA_PATH, label="trusted job")
        without_hash = {
            key: value
            for key, value in checked_job.items()
            if key != "jobCanonicalSha256"
        }
        observed_hash = canonical_sha256(without_hash)
        if (
            checked_job["jobId"] != entry["jobId"]
            or checked_job["target"]["directoryId"] != entry["targetRecordId"]
            or checked_job["jobCanonicalSha256"] != entry["jobCanonicalSha256"]
            or observed_hash != entry["jobCanonicalSha256"]
        ):
            raise ModelHandoffError(
                f"trusted job artifact does not match manifest: {entry['jobId']}"
            )

        for authority in checked_job["officialAuthorities"]:
            authority_id = authority["authorityId"]
            identity = (
                authority["publisher"],
                authority["governmentLevel"],
                tuple(sorted(authority["domains"])),
            )
            previous_identity = authority_identities.get(authority_id)
            if previous_identity is not None and previous_identity != identity:
                raise ModelHandoffError(
                    "trusted jobs reuse an authorityId with a different "
                    f"identity: {authority_id}"
                )
            authority_identities[authority_id] = identity

        packet_path_value = entry.get("packetPath")
        packet_digest = entry.get("packetCanonicalSha256")
        if checked_job["taskType"] == "extract-candidates":
            if not isinstance(packet_path_value, str) or not isinstance(
                packet_digest,
                str,
            ):
                raise ModelHandoffError(
                    "trusted classification job requires a pinned packet"
                )
            packet_path = _trusted_relative_path(
                packet_path_value,
                label=f"trusted job {entry['jobId']} packetPath",
            )
            checked_packet = load_strict_json(packet_path)
            if not isinstance(checked_packet, dict):
                raise ModelHandoffError("trusted packet root must be an object")
            _validate_schema(
                checked_packet,
                PREFETCHED_PACKET_SCHEMA_PATH,
                label="trusted prefetched packet",
            )
            observed_packet_hash = canonical_sha256(
                {
                    key: value
                    for key, value in checked_packet.items()
                    if key != "packetCanonicalSha256"
                }
            )
            if (
                checked_packet["jobId"] != checked_job["jobId"]
                or checked_packet["jobCanonicalSha256"]
                != checked_job["jobCanonicalSha256"]
                or checked_packet["taskType"] != checked_job["taskType"]
                or checked_packet["packetCanonicalSha256"] != packet_digest
                or observed_packet_hash != packet_digest
            ):
                raise ModelHandoffError(
                    f"trusted packet artifact does not match manifest: "
                    f"{entry['jobId']}"
                )
        elif packet_path_value is not None or packet_digest is not None:
            raise ModelHandoffError(
                "source-discovery jobs cannot pin a classification packet"
            )
    return manifest, directories


def _find_trusted_job_entry(
    job: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> Mapping[str, Any]:
    matches = [
        entry
        for entry in manifest["jobs"]
        if entry["jobId"] == job["jobId"]
        and entry["jobCanonicalSha256"] == job["jobCanonicalSha256"]
    ]
    if len(matches) != 1:
        raise ModelHandoffError(
            "job is not present in the checked-in trusted job manifest"
        )
    entry = matches[0]
    if entry["targetRecordId"] != job["target"]["directoryId"]:
        raise ModelHandoffError("job target is not bound to its trusted record id")
    return entry


def trusted_packet_binding(job: Mapping[str, Any]) -> dict[str, str] | None:
    """Return the reviewed packet binding for a trusted classification job."""

    manifest, _directories = _load_trusted_job_manifest()
    entry = _find_trusted_job_entry(job, manifest)
    packet_path = entry.get("packetPath")
    packet_digest = entry.get("packetCanonicalSha256")
    if job["taskType"] != "extract-candidates":
        if packet_path is not None or packet_digest is not None:
            raise ModelHandoffError(
                "source-discovery job has an unexpected packet binding"
            )
        return None
    if not isinstance(packet_path, str) or not isinstance(packet_digest, str):
        raise ModelHandoffError(
            "classification job is missing its trusted packet binding"
        )
    return {
        "path": packet_path,
        "packetCanonicalSha256": packet_digest,
    }


def _directory_record_id(record: Mapping[str, Any]) -> Any:
    if "directoryId" in record:
        return record.get("directoryId")
    if "id" in record:
        return record.get("id")
    body = record.get("body")
    if isinstance(body, Mapping):
        return body.get("id")
    return None


def _validate_target_against_directory(
    target: Mapping[str, Any],
    directory: Mapping[str, Any],
    *,
    target_record_id: str | None = None,
) -> None:
    jurisdiction = _normalize_jurisdiction(
        directory.get("jurisdiction"),
        label="trusted target directory jurisdiction",
    )
    if jurisdiction != f"CA-{target['provinceTerritory']}":
        raise ModelHandoffError(
            "job province does not match the trusted target directory jurisdiction"
        )
    records = directory.get("records")
    if not isinstance(records, list):
        raise ModelHandoffError("trusted target directory records must be an array")
    record_id = target_record_id or str(target["directoryId"])
    if record_id != target["directoryId"]:
        raise ModelHandoffError(
            "job target directoryId does not match its trusted targetRecordId"
        )
    matches = [
        record
        for record in records
        if isinstance(record, Mapping)
        and _directory_record_id(record) == record_id
    ]
    if len(matches) != 1:
        raise ModelHandoffError(
            "job target directoryId does not resolve exactly once in the "
            "trusted directory"
        )
    record = matches[0]
    if "directoryId" in record:
        expected = {
            "assessmentCode": target["assessmentCode"],
            "displayName": target["displayName"],
            "officialName": target["officialName"],
            "tier": target["governmentTier"],
            "geographicArea": target["geographicArea"],
        }
        mismatches = [
            key for key, value in expected.items() if record.get(key) != value
        ]
    else:
        if (
            directory.get("schemaVersion")
            != "auditback-canonical-government-directory-3.0.0"
        ):
            raise ModelHandoffError(
                "generic target binding requires the canonical government "
                "directory schema"
            )
        generic = record
        official_names = generic.get("officialNames")
        external_ids = generic.get("externalIds")
        external_id_namespace = target.get("externalIdNamespace")
        geography_ids = target.get("governsGeographyIds")
        parent_body = target.get("parentBody")
        mismatches = []
        if (
            not isinstance(official_names, Mapping)
            or target["officialName"] not in official_names.values()
        ):
            mismatches.append("officialName")
        if (
            not isinstance(external_id_namespace, str)
            or not isinstance(external_ids, Mapping)
            or external_ids.get(external_id_namespace) != target["assessmentCode"]
        ):
            mismatches.append("assessmentCode")
        if generic.get("governmentTier") != target["governmentTier"]:
            mismatches.append("governmentTier")
        if generic.get("provinceTerritory") != target["provinceTerritory"]:
            mismatches.append("provinceTerritory")
        if generic.get("status") != "active":
            mismatches.append("status")
        if (
            not isinstance(geography_ids, list)
            or set(generic.get("governsGeographyIds", [])) != set(geography_ids)
        ):
            mismatches.append("governsGeographyIds")
        if parent_body is None:
            expected_parent_ids: list[str] = []
        else:
            parent_id = parent_body.get("directoryId")
            expected_parent_ids = [parent_id] if isinstance(parent_id, str) else []
            if not expected_parent_ids:
                mismatches.append("parentBody.directoryId")
        if set(generic.get("parentBodyIds", [])) != set(expected_parent_ids):
            mismatches.append("parentBodyIds")
    if mismatches:
        raise ModelHandoffError(
            "job target does not match the trusted directory fields: "
            + ", ".join(mismatches)
        )


def _document_key(value: Mapping[str, Any]) -> tuple[str, str, str, int]:
    return (
        str(value["documentType"]),
        str(value["authorityId"]),
        str(value["governmentLevel"]),
        int(value["fiscalYear"]),
    )


def _validate_date(value: str, *, label: str) -> None:
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ModelHandoffError(f"{label} must be a real ISO calendar date") from exc


def _validate_timestamp(value: str, *, label: str) -> None:
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError) as exc:
        raise ModelHandoffError(
            f"{label} must be a real UTC timestamp ending in Z"
        ) from exc


def _validate_official_url(
    url: str,
    allowed_domains: Iterable[str],
    *,
    label: str,
) -> str:
    if any(character.isspace() for character in url) or "\\" in url:
        raise ModelHandoffError(f"{label} contains whitespace or a backslash")
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ModelHandoffError(f"{label} is not a valid HTTPS URL") from exc
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        raise ModelHandoffError(
            f"{label} must use HTTPS without credentials or a non-443 port"
        )
    host = hostname.rstrip(".").lower()
    try:
        host.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ModelHandoffError(f"{label} hostname must be ASCII") from exc
    allowed = tuple(domain.lower().rstrip(".") for domain in allowed_domains)
    if not any(host == domain or host.endswith(f".{domain}") for domain in allowed):
        raise ModelHandoffError(
            f"{label} host {host!r} is outside its official authority lane"
        )
    return host


def _host_matches_domains(host: str, domains: Iterable[str]) -> bool:
    return any(
        host == domain.lower().rstrip(".")
        or host.endswith(f".{domain.lower().rstrip('.')}")
        for domain in domains
    )


def _authority_by_id(
    job: Mapping[str, Any],
    authority_id: str,
) -> Mapping[str, Any]:
    matches = [
        authority
        for authority in job["officialAuthorities"]
        if authority["authorityId"] == authority_id
    ]
    if len(matches) != 1:
        raise ModelHandoffError(
            f"authorityId must resolve exactly once in the job: {authority_id}"
        )
    return matches[0]


def _validate_source_authority(
    job: Mapping[str, Any],
    source: Mapping[str, Any],
    *,
    label: str,
) -> None:
    authority = _authority_by_id(job, source["authorityId"])
    if source["governmentLevel"] != authority["governmentLevel"]:
        raise ModelHandoffError(
            f"{label} authorityId and governmentLevel do not match"
        )
    host = _validate_official_url(source["url"], authority["domains"], label=label)
    if (
        source["publisher"] != authority["publisher"]
        or not _host_matches_domains(host, authority["domains"])
    ):
        raise ModelHandoffError(
            f"{label} authorityId, publisher, host, and governmentLevel do not "
            "match the same official authority lane"
        )


def _walk_strings(value: Any, path: str = "<root>") -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield from _walk_strings(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_strings(item, f"{path}[{index}]")


def _reject_sensitive_text(value: Mapping[str, Any]) -> None:
    for location, text in _walk_strings(value):
        if _LOCAL_PATH_PATTERN.search(text):
            raise ModelHandoffError(
                f"candidate contains a local filesystem path at {location}"
            )
        if any(pattern.search(text) for pattern in _SECRET_PATTERNS):
            raise ModelHandoffError(
                f"candidate contains credential-like text at {location}"
            )
        if _EMAIL_ADDRESS_PATTERN.search(text):
            raise ModelHandoffError(
                f"candidate contains an email address at {location}"
            )
        if _PHONE_LIKE_PATTERN.search(text):
            raise ModelHandoffError(
                f"candidate contains a phone number at {location}"
            )
        if not location.casefold().endswith("sha256") and _contains_valid_canadian_sin(
            text
        ):
            raise ModelHandoffError(
                f"candidate contains a valid SIN-like identifier at {location}"
            )


def _validate_source_semantics(source: Mapping[str, Any], *, source_key: str) -> None:
    issue_codes = set(source["issueCodes"])
    publication_unknown = source["publicationDate"] is None
    if publication_unknown != ("date-unclear" in issue_codes):
        raise ModelHandoffError(
            f"source {source_key} must use date-unclear exactly when "
            "publicationDate is null"
        )

    status_unknown = source["adoptionStatus"] == "unknown"
    if status_unknown != ("status-unclear" in issue_codes):
        raise ModelHandoffError(
            f"source {source_key} must use status-unclear exactly when "
            "adoptionStatus is unknown"
        )

    excerpt_unknown = source["exactExcerpt"] is None
    if excerpt_unknown != ("excerpt-not-captured" in issue_codes):
        raise ModelHandoffError(
            f"source {source_key} must use excerpt-not-captured exactly when "
            "exactExcerpt is null"
        )
    if not excerpt_unknown and source["locator"] is None:
        raise ModelHandoffError(
            f"source {source_key} with an exactExcerpt requires a locator"
        )
    provenance_core = (
        source["retrievedAt"],
        source["contentType"],
        source["sourceContentSha256"],
    )
    if any(value is None for value in provenance_core) != all(
        value is None for value in provenance_core
    ):
        raise ModelHandoffError(
            f"source {source_key} retrieval provenance must be wholly captured "
            "or wholly null"
        )
    if source["retrievedAt"] is not None:
        _validate_timestamp(
            source["retrievedAt"],
            label=f"source {source_key} retrievedAt",
        )
    excerpt_digest = source["exactExcerptUtf8Sha256"]
    if excerpt_unknown != (excerpt_digest is None):
        raise ModelHandoffError(
            f"source {source_key} exactExcerptUtf8Sha256 must be null exactly "
            "when exactExcerpt is null"
        )
    if excerpt_digest is not None:
        observed_excerpt_digest = hashlib.sha256(
            source["exactExcerpt"].encode("utf-8")
        ).hexdigest()
        if observed_excerpt_digest != excerpt_digest:
            raise ModelHandoffError(
                f"source {source_key} exactExcerptUtf8Sha256 does not match "
                "exactExcerpt"
            )

    allowed_statuses = {
        "approved-budget": {"approved", "draft", "unknown"},
        "final-tax-rate-instrument": {"final", "draft", "unknown"},
        "service-allocation-schedule": {
            "approved",
            "final",
            "draft",
            "unknown",
        },
    }[source["documentType"]]
    if source["adoptionStatus"] not in allowed_statuses:
        raise ModelHandoffError(
            f"source {source_key} adoptionStatus is incompatible with "
            f"{source['documentType']}"
        )


def _non_closing_gap_reasons(source: Mapping[str, Any]) -> set[str]:
    issue_codes = set(source["issueCodes"])
    if source["adoptionStatus"] == "draft":
        return {"only-draft-found"}
    if (
        source["adoptionStatus"] == "unknown"
        or "status-unclear" in issue_codes
    ):
        return {"status-unclear"}
    if "mixed-year-risk" in issue_codes:
        return {"year-unclear"}
    if issue_codes & {"accounting-basis-unclear", "possible-duplicate"}:
        return {"conflicting-sources"}
    if source["exactExcerpt"] is None or "excerpt-not-captured" in issue_codes:
        return {"access-failed"}
    return set()


def validate_job(job: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a hash-bound, provider-neutral municipal job."""

    if not isinstance(job, Mapping):
        raise ModelHandoffError("job root must be an object")
    _validate_schema(job, JOB_SCHEMA_PATH, label="job")

    without_hash = {
        key: value for key, value in job.items() if key != "jobCanonicalSha256"
    }
    expected_hash = canonical_sha256(without_hash)
    if job["jobCanonicalSha256"] != expected_hash:
        raise ModelHandoffError("jobCanonicalSha256 does not match job content")

    if job["taskType"] == "extract-candidates" and any(
        job["budget"][field] != 0
        for field in (
            "maxWebSearches",
            "maxWebFetches",
            "maxPdfPagesPerDocument",
        )
    ):
        raise ModelHandoffError(
            "extract-candidates jobs must disable web search, web fetch, and "
            "PDF page access"
        )

    manifest, directories = _load_trusted_job_manifest()
    trusted_entry = _find_trusted_job_entry(job, manifest)
    directory = directories[trusted_entry["targetDirectoryPath"]]

    years = list(job["targetFiscalYears"])
    if years != sorted(years, reverse=True):
        raise ModelHandoffError("targetFiscalYears must be newest first")

    target = job["target"]
    expected_prefix = (
        f"{target['provinceTerritory']}-{target['assessmentCode']}-FY"
        f"{years[0]}-"
    )
    if not str(job["jobId"]).startswith(expected_prefix):
        raise ModelHandoffError(
            "jobId must bind the province, assessment code, and newest fiscal year"
        )

    levels = set(job["requiredGovernmentLevels"])
    authority_levels: set[str] = set()
    authority_ids: set[str] = set()
    for authority in job["officialAuthorities"]:
        authority_id = authority["authorityId"]
        if authority_id in authority_ids:
            raise ModelHandoffError(
                f"officialAuthorities contains a duplicate authorityId: "
                f"{authority_id}"
            )
        authority_ids.add(authority_id)
        authority_levels.add(authority["governmentLevel"])
    if authority_levels != levels:
        raise ModelHandoffError(
            "officialAuthorities must cover exactly the requiredGovernmentLevels"
        )

    documents = list(job["requestedDocuments"])
    document_keys = [_document_key(document) for document in documents]
    if len(document_keys) != len(set(document_keys)):
        raise ModelHandoffError("requestedDocuments contains a duplicate request")
    for document in documents:
        if document["fiscalYear"] not in years:
            raise ModelHandoffError(
                "requested document fiscalYear is outside targetFiscalYears"
            )
        if document["governmentLevel"] not in levels:
            raise ModelHandoffError(
                "requested document governmentLevel is not required by the job"
            )
        authority = _authority_by_id(job, document["authorityId"])
        if document["governmentLevel"] != authority["governmentLevel"]:
            raise ModelHandoffError(
                "requested document authorityId and governmentLevel do not match"
            )

    tier = target["governmentTier"]
    if tier not in levels:
        raise ModelHandoffError("target governmentTier must be a required level")
    if tier == "lower-tier":
        if target["parentBody"] is None or "upper-tier" not in levels:
            raise ModelHandoffError(
                "a lower-tier job requires its upper-tier parent and evidence lane"
            )
    elif target["parentBody"] is not None:
        raise ModelHandoffError(
            "only a lower-tier target may carry an upper-tier parentBody"
        )
    if tier == "lower-tier":
        upper_publishers = {
            authority["publisher"]
            for authority in job["officialAuthorities"]
            if authority["governmentLevel"] == "upper-tier"
        }
        if target["parentBody"]["officialName"] not in upper_publishers:
            raise ModelHandoffError(
                "lower-tier parentBody must match an upper-tier official authority"
            )

    _validate_target_against_directory(
        target,
        directory,
        target_record_id=trusted_entry["targetRecordId"],
    )
    return dict(job)


def validate_candidate(
    job: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one untrusted candidate against its exact job.

    A successful result means only that the candidate is safe to enter the next
    verification queue. It does not verify a source or approve publication.
    """

    validated_job = validate_job(job)
    if not isinstance(candidate, Mapping):
        raise ModelHandoffError("candidate root must be an object")
    _validate_schema(candidate, CANDIDATE_SCHEMA_PATH, label="candidate")
    _reject_sensitive_text(candidate)

    if candidate["jobId"] != validated_job["jobId"]:
        raise ModelHandoffError("candidate jobId does not match the selected job")
    if candidate["jobCanonicalSha256"] != validated_job["jobCanonicalSha256"]:
        raise ModelHandoffError(
            "candidate jobCanonicalSha256 does not match the selected job"
        )
    if validated_job["taskType"] == "discover-sources":
        if candidate["packetCanonicalSha256"] is not None:
            raise ModelHandoffError(
                "source-discovery candidate packetCanonicalSha256 must be null"
            )
    elif candidate["packetCanonicalSha256"] is None:
        raise ModelHandoffError(
            "extract-candidates candidate requires packetCanonicalSha256"
        )
    if candidate["target"] != validated_job["target"]:
        raise ModelHandoffError("candidate target does not exactly match the job")

    _validate_timestamp(
        candidate["producer"]["runBindingAt"],
        label="producer.runBindingAt",
    )
    requested = {
        _document_key(document): bool(document["required"])
        for document in validated_job["requestedDocuments"]
    }

    source_keys: set[str] = set()
    source_document_keys: set[tuple[str, str, str, int]] = set()
    closing_source_document_keys: set[tuple[str, str, str, int]] = set()
    non_closing_reasons: dict[tuple[str, str, str, int], set[str]] = {}
    for index, source in enumerate(candidate["sources"]):
        source_key = source["sourceKey"]
        if source_key in source_keys:
            raise ModelHandoffError(f"duplicate sourceKey is forbidden: {source_key}")
        source_keys.add(source_key)
        document_key = _document_key(source)
        if document_key not in requested:
            raise ModelHandoffError(
                f"candidate source {source_key} does not answer a requested document"
            )
        source_document_keys.add(document_key)
        _validate_source_authority(
            validated_job,
            source,
            label=f"sources[{index}].url",
        )
        if source["publicationDate"] is not None:
            _validate_date(
                source["publicationDate"],
                label=f"sources[{index}].publicationDate",
            )
        _validate_source_semantics(source, source_key=source_key)
        reasons = _non_closing_gap_reasons(source)
        if reasons:
            non_closing_reasons.setdefault(document_key, set()).update(reasons)
        else:
            closing_source_document_keys.add(document_key)

    gap_document_keys: set[tuple[str, str, str, int]] = set()
    gap_reasons: dict[tuple[str, str, str, int], str] = {}
    for index, gap in enumerate(candidate["gaps"]):
        document_key = _document_key(gap)
        if document_key not in requested:
            raise ModelHandoffError(
                f"candidate gap {index} does not answer a requested document"
            )
        if document_key in gap_document_keys:
            raise ModelHandoffError(
                f"duplicate gap for requested document: {document_key}"
            )
        gap_document_keys.add(document_key)
        gap_reasons[document_key] = gap["reasonCode"]
        if gap["reasonCode"] == "not-yet-researched":
            if gap["searchTrail"]:
                raise ModelHandoffError(
                    f"candidate gap {index} marked not-yet-researched must have "
                    "an empty searchTrail"
                )
        elif not gap["searchTrail"]:
            raise ModelHandoffError(
                f"candidate gap {index} reason {gap['reasonCode']} requires "
                "an official searchTrail"
            )
        authority = _authority_by_id(validated_job, gap["authorityId"])
        if gap["governmentLevel"] != authority["governmentLevel"]:
            raise ModelHandoffError(
                f"candidate gap {index} authorityId and governmentLevel do "
                "not match"
            )
        for trail_index, trail in enumerate(gap["searchTrail"]):
            if trail["authorityId"] != gap["authorityId"]:
                raise ModelHandoffError(
                    f"candidate gap {index} searchTrail authorityId does not "
                    "match the gap authority"
                )
            _validate_official_url(
                trail["url"],
                authority["domains"],
                label=f"gaps[{index}].searchTrail[{trail_index}]",
            )

    overlap = source_document_keys & gap_document_keys
    for document_key in sorted(overlap):
        expected_reasons = non_closing_reasons.get(document_key, set())
        actual_reason = gap_reasons[document_key]
        if actual_reason not in expected_reasons:
            raise ModelHandoffError(
                "source and gap overlap is allowed only for an explicit "
                f"non-closing evidence reason: {document_key}"
            )

    for document_key, expected_reasons in non_closing_reasons.items():
        if document_key in closing_source_document_keys:
            continue
        if gap_reasons.get(document_key) not in expected_reasons:
            raise ModelHandoffError(
                "non-closing source requires a matching gap for requested "
                f"document: {document_key}"
            )

    required_keys = {key for key, required in requested.items() if required}
    covered_keys = closing_source_document_keys | gap_document_keys
    missing = sorted(required_keys - covered_keys)
    if missing:
        raise ModelHandoffError(
            f"candidate omits required source-or-gap decisions: {missing}"
        )

    outcome = candidate["outcome"]
    if outcome == "complete":
        if (
            candidate["gaps"]
            or non_closing_reasons
            or not required_keys.issubset(closing_source_document_keys)
        ):
            raise ModelHandoffError(
                "outcome complete requires closing final/approved sources for "
                "every required document, no non-closing sources, and no gaps"
            )
    elif outcome == "partial":
        if not candidate["sources"] or not candidate["gaps"]:
            raise ModelHandoffError(
                "outcome partial requires at least one source and one gap"
            )
    elif outcome == "no-official-source-found":
        if candidate["sources"] or not required_keys.issubset(gap_document_keys):
            raise ModelHandoffError(
                "outcome no-official-source-found requires zero sources and "
                "a gap for every required document"
            )

    return {
        "valid": True,
        "jobId": validated_job["jobId"],
        "targetRecordId": validated_job["target"]["directoryId"],
        "status": "pending-human-review",
        "outcome": outcome,
        "sourceCount": len(candidate["sources"]),
        "gapCount": len(candidate["gaps"]),
        "candidateCanonicalSha256": canonical_sha256(candidate),
        "networkRequestsMade": 0,
        "canonicalDataWritten": False,
        "mayPublish": False,
    }


def validate_handoff_files(
    job_path: str | Path,
    candidate_path: str | Path,
    packet_path: str | Path | None = None,
) -> dict[str, Any]:
    job = load_strict_json(job_path)
    candidate = load_strict_json(candidate_path)
    result = validate_candidate(job, candidate)
    if job["taskType"] == "extract-candidates":
        if packet_path is None:
            raise ModelHandoffError(
                "extract-candidates validation requires the trusted packet"
            )
        from .subscription_provider_runner import (  # local to avoid import cycle
            validate_candidate_packet_binding,
            validate_prefetched_packet,
        )

        packet = load_strict_json(packet_path)
        validated_job = validate_job(job)
        validated_packet = validate_prefetched_packet(
            validated_job,
            packet,
            require_trusted=True,
        )
        validate_candidate_packet_binding(
            validated_job,
            validated_packet,
            candidate,
        )
    elif packet_path is not None:
        raise ModelHandoffError(
            "discover-sources validation does not accept a packet"
        )
    return result
