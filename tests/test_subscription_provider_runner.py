from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from national.model_handoff import load_strict_json
from national.models import canonical_json_bytes, canonical_sha256
from national.subscription_provider_runner import (
    AGY_AGENT_NAME,
    AGY_MODEL,
    CLAUDE_MODEL,
    MAX_STDOUT_UTF8_BYTES,
    BoundedProcessResult,
    SubscriptionProviderError,
    _CLAUDE_CLASSIFIER_SYSTEM_PROMPT,
    _CLAUDE_INLINE_SETTINGS,
    _assert_agy_subscription_settings,
    _consume_agy_auth_preflight_log,
    _verify_trusted_executable,
    run_subscription_provider,
    validate_candidate_packet_binding,
    validate_prefetched_packet,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_JOB = (
    ROOT
    / "handoffs"
    / "jobs"
    / "ontario-waterloo-2026"
    / "02-wellesley"
    / "job.json"
)
RUN_BINDING_AT = "2026-07-27T12:00:00Z"


def _identity_job(job: object) -> dict:
    if not isinstance(job, dict):
        return copy.deepcopy(dict(job))  # type: ignore[arg-type]
    return copy.deepcopy(job)


def _rehash_job(job: dict) -> dict:
    job["jobCanonicalSha256"] = canonical_sha256(
        {
            key: value
            for key, value in job.items()
            if key != "jobCanonicalSha256"
        }
    )
    return job


def _rehash_packet(packet: dict) -> dict:
    packet["packetCanonicalSha256"] = canonical_sha256(
        {
            key: value
            for key, value in packet.items()
            if key != "packetCanonicalSha256"
        }
    )
    return packet


def _extract_job() -> dict:
    job = copy.deepcopy(load_strict_json(SOURCE_JOB))
    job["taskType"] = "extract-candidates"
    job["budget"]["maxWebSearches"] = 0
    job["budget"]["maxWebFetches"] = 0
    job["budget"]["maxPdfPagesPerDocument"] = 0
    job["budget"]["maxModelTurns"] = 1
    return _rehash_job(job)


def _first_required(job: dict) -> dict:
    return next(
        item
        for item in job["requestedDocuments"]
        if item["required"] and item["documentType"] == "approved-budget"
    )


def _packet(job: dict) -> dict:
    requested = _first_required(job)
    authority = next(
        item
        for item in job["officialAuthorities"]
        if item["authorityId"] == requested["authorityId"]
    )
    excerpt = "Council approved the 2026 operating and capital budget."
    source = {
        "sourceKey": "S1",
        "url": "https://www.wellesley.ca/council-and-administration/budget/",
        "publisher": authority["publisher"],
        "title": "2026 approved budget",
        "documentType": requested["documentType"],
        "authorityId": requested["authorityId"],
        "governmentLevel": requested["governmentLevel"],
        "fiscalYear": requested["fiscalYear"],
        "publicationDate": "2026-01-13",
        "retrievedAt": "2026-07-27T11:30:00Z",
        "contentType": "text/html",
        "locator": "Budget page, approval notice",
        "exactExcerpt": excerpt,
        "sourceContentSha256": hashlib.sha256(
            b"deterministically-prefetched-source"
        ).hexdigest(),
        "exactExcerptUtf8Sha256": hashlib.sha256(
            excerpt.encode("utf-8")
        ).hexdigest(),
    }
    return _rehash_packet(
        {
            "schemaVersion": "whatinthetax-prefetched-source-packet-1.0.0",
            "jobId": job["jobId"],
            "jobCanonicalSha256": job["jobCanonicalSha256"],
            "taskType": "extract-candidates",
            "assembledAt": "2026-07-27T11:45:00Z",
            "sources": [source],
            "packetCanonicalSha256": "0" * 64,
        }
    )


def _candidate(job: dict, packet: dict, provider: str, model: str) -> dict:
    copied_fields = (
        "sourceKey",
        "authorityId",
        "url",
        "publisher",
        "title",
        "documentType",
        "governmentLevel",
        "fiscalYear",
        "publicationDate",
        "retrievedAt",
        "contentType",
        "locator",
        "exactExcerpt",
        "sourceContentSha256",
        "exactExcerptUtf8Sha256",
    )
    sources = []
    source_document_keys = set()
    for prefetched in packet["sources"]:
        source = {
            key: copy.deepcopy(prefetched[key])
            for key in copied_fields
        }
        source.update(
            {
                "adoptionStatus": "approved",
                "issueCodes": [],
                "secondCheckRequired": True,
            }
        )
        sources.append(source)
        source_document_keys.add(
            (
                source["documentType"],
                source["authorityId"],
                source["governmentLevel"],
                source["fiscalYear"],
            )
        )
    gaps = []
    for requested in job["requestedDocuments"]:
        key = (
            requested["documentType"],
            requested["authorityId"],
            requested["governmentLevel"],
            requested["fiscalYear"],
        )
        if requested["required"] and key not in source_document_keys:
            gaps.append(
                {
                    "documentType": requested["documentType"],
                    "authorityId": requested["authorityId"],
                    "governmentLevel": requested["governmentLevel"],
                    "fiscalYear": requested["fiscalYear"],
                    "reasonCode": "not-yet-researched",
                    "searchTrail": [],
                    "note": "No supplied excerpt supports this required document.",
                }
            )
    return {
        "schemaVersion": "whatinthetax-municipal-evidence-candidate-1.0.0",
        "jobId": job["jobId"],
        "jobCanonicalSha256": job["jobCanonicalSha256"],
        "packetCanonicalSha256": packet["packetCanonicalSha256"],
        "target": copy.deepcopy(job["target"]),
        "producer": {
            "provider": provider,
            "model": model,
            "accessMode": "subscription-cli",
            "runBindingAt": RUN_BINDING_AT,
        },
        "status": "pending-human-review",
        "outcome": "partial",
        "humanReviewRequired": True,
        "mayAutoPublish": False,
        "sources": sources,
        "gaps": gaps,
    }


def _claude_result(candidate: object) -> dict:
    return {
        "type": "result",
        "subtype": "success",
        "duration_ms": 1250,
        "duration_api_ms": 950,
        "is_error": False,
        "num_turns": 1,
        "result": canonical_json_bytes(candidate).decode("utf-8"),
        "stop_reason": "end_turn",
        "total_cost_usd": 0.0125,
        "usage": {
            "input_tokens": 1200,
            "output_tokens": 450,
        },
        "modelUsage": {
            CLAUDE_MODEL: {
                "inputTokens": 1200,
                "outputTokens": 450,
                "costUSD": 0.0125,
            }
        },
        "permission_denials": [],
        "uuid": "550e8400-e29b-41d4-a716-446655440000",
        "session_id": "550e8400-e29b-41d4-a716-446655440001",
        "terminal_reason": "completed",
    }


class FakeProviderProcess:
    def __init__(self, provider: str, candidate: dict) -> None:
        self.provider = provider
        final_value: object = (
            _claude_result(candidate)
            if provider == "claude"
            else candidate
        )
        self.candidate_bytes = canonical_json_bytes(final_value)
        self.calls: list[dict] = []

    def __call__(self, command: list[str], **kwargs: object) -> BoundedProcessResult:
        self.calls.append(
            {
                "command": list(command),
                "cwd": kwargs["cwd"],
                "env": copy.deepcopy(kwargs["env"]),
                "input_bytes": kwargs["input_bytes"],
            }
        )
        stderr = b""
        if command[-1] == "--version":
            value = b"1.1.7\n" if self.provider == "agy" else b"2.1.220 (Claude Code)\n"
        elif command[-1] == "--help":
            if self.provider == "agy":
                value = (
                    b"--add-dir --agent --effort --log-file --mode --model --print "
                    b"--print-timeout --sandbox"
                )
                stderr = value
                value = b""
            else:
                value = (
                    b"--disable-slash-commands --effort "
                    b"--mcp-config --model "
                    b"--no-chrome --no-session-persistence "
                    b"--output-format "
                    b"--permission-mode --print --safe-mode "
                    b"--setting-sources --settings "
                    b"--strict-mcp-config --system-prompt --tools"
                )
        elif command[-1] == "agent":
            value = f"Available agents:\n{AGY_AGENT_NAME}\n".encode()
        elif command[-1] == "models":
            log_path = Path(command[command.index("--log-file") + 1])
            log_path.write_text(
                "You are not logged into Antigravity.\n"
                "OAuth: authenticated successfully as saved subscription user\n"
                "v1internal:fetchAvailableModels\n",
                encoding="utf-8",
            )
            value = f"{AGY_MODEL}\n".encode()
        elif command[-2:] == ["auth", "status"]:
            value = json.dumps(
                {
                    "loggedIn": True,
                    "authMethod": "claude.ai",
                    "apiProvider": "firstParty",
                    "subscriptionType": "max",
                }
            ).encode()
        else:
            value = self.candidate_bytes
        return BoundedProcessResult(returncode=0, stdout=value, stderr=stderr)


class SubscriptionProviderRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.job = _extract_job()
        self.packet = _packet(self.job)
        self.trusted_packet_digest = self.packet["packetCanonicalSha256"]
        self.runner_patch = patch(
            "national.subscription_provider_runner.validate_job",
            side_effect=_identity_job,
        )
        self.candidate_job_patch = patch(
            "national.model_handoff.validate_job",
            side_effect=_identity_job,
        )
        self.runner_patch.start()
        self.candidate_job_patch.start()
        self.addCleanup(self.runner_patch.stop)
        self.addCleanup(self.candidate_job_patch.stop)
        self.packet_binding_patch = patch(
            "national.subscription_provider_runner.trusted_packet_binding",
            side_effect=self._trusted_packet_binding,
        )
        self.packet_binding_patch.start()
        self.addCleanup(self.packet_binding_patch.stop)
        self.binary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.binary_directory.cleanup)

    def _trusted_packet_binding(self, job: object) -> dict[str, str]:
        del job
        return {
            "path": "unit-test-packet.json",
            "packetCanonicalSha256": self.trusted_packet_digest,
        }

    def _resolver(self, name: str, environ: object) -> Path:
        del environ
        path = Path(self.binary_directory.name) / f"{name}.exe"
        path.write_bytes(b"mock executable")
        return path.resolve()

    def _verifier(
        self,
        name: str,
        path: Path,
        environ: object,
    ) -> None:
        del name, path, environ

    def test_default_is_dry_run_and_never_resolves_or_invokes_cli(self) -> None:
        def forbidden_resolver(name: str, environ: object) -> Path:
            raise AssertionError(f"unexpected resolver call: {name} {environ}")

        def forbidden_runner(*args: object, **kwargs: object) -> BoundedProcessResult:
            raise AssertionError(f"unexpected process call: {args} {kwargs}")

        result = run_subscription_provider(
            self.job,
            self.packet,
            provider="claude",
            environ={},
            process_runner=forbidden_runner,
            executable_resolver=forbidden_resolver,
            run_binding_at=RUN_BINDING_AT,
        )
        self.assertTrue(result["dryRun"])
        self.assertFalse(result["invokesModel"])
        self.assertTrue(result["liveEligible"])
        self.assertFalse(result["writesRepository"])
        self.assertFalse(result["mayPublish"])
        self.assertLessEqual(result["promptUtf8Bytes"], 20_000)
        self.assertEqual(result["outputFormat"], "json")
        self.assertEqual(
            result["structuredOutputMode"],
            "single-json-result-string",
        )
        self.assertEqual(result["maxModelTurns"], 1)
        self.assertEqual(result["runBindingAt"], RUN_BINDING_AT)
        self.assertNotIn("completedAt", result)
        self.assertNotIn("structuredOutputSchemaDraft", result)
        self.assertNotIn("structuredOutputSchemaUtf8Bytes", result)
        self.assertLess(result["promptUtf8Bytes"], 20_000)
        self.assertGreater(
            result["maxStdoutBytes"],
            self.job["budget"]["maxOutputTokens"] * 8,
        )

    def test_live_controls_must_be_exact_booleans_before_cli_resolution(
        self,
    ) -> None:
        def forbidden_resolver(name: str, environ: object) -> Path:
            raise AssertionError(f"unexpected resolver call: {name} {environ}")

        cases = (
            (1, True),
            ("true", True),
            (False, 1),
        )
        for execute, confirm in cases:
            with self.subTest(execute=execute, confirm=confirm):
                with self.assertRaisesRegex(
                    SubscriptionProviderError,
                    "exact booleans",
                ):
                    run_subscription_provider(
                        self.job,
                        self.packet,
                        provider="claude",
                        execute=execute,  # type: ignore[arg-type]
                        confirm_subscription_usage=confirm,  # type: ignore[arg-type]
                        environ={},
                        executable_resolver=forbidden_resolver,
                        run_binding_at=RUN_BINDING_AT,
                    )

    def test_credentials_and_ci_are_refused_even_for_dry_run(self) -> None:
        with self.assertRaisesRegex(
            SubscriptionProviderError,
            "credential or alternate-billing",
        ):
            run_subscription_provider(
                self.job,
                self.packet,
                provider="claude",
                environ={"ANTHROPIC_API_KEY": "forbidden"},
            )
        with self.assertRaisesRegex(SubscriptionProviderError, "CI/automation"):
            run_subscription_provider(
                self.job,
                self.packet,
                provider="agy",
                environ={"CI": "true"},
            )

    def test_agy_personal_credit_fallback_is_refused(self) -> None:
        profile = Path(self.binary_directory.name) / "profile"
        settings_directory = profile / ".gemini" / "antigravity-cli"
        settings_directory.mkdir(parents=True)
        (settings_directory / "settings.json").write_text(
            '{"useG1Credits":true}',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            SubscriptionProviderError,
            "personal AI-credit fallback",
        ):
            _assert_agy_subscription_settings(
                {"USERPROFILE": str(profile)}
            )

    def test_agy_auth_log_requires_later_oauth_success_and_is_removed(self) -> None:
        working_directory = Path(self.binary_directory.name).resolve()
        log_path = working_directory / "agy-auth-preflight.log"
        log_path.write_text(
            "You are not logged into Antigravity.\n"
            "v1internal:fetchAvailableModels\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            SubscriptionProviderError,
            "active saved subscription login",
        ):
            _consume_agy_auth_preflight_log(
                log_path,
                working_directory=working_directory,
            )
        self.assertFalse(log_path.exists())

    def test_packet_is_closed_hash_bound_and_authority_bound(self) -> None:
        changed = copy.deepcopy(self.packet)
        changed["unexpected"] = True
        _rehash_packet(changed)
        with self.assertRaisesRegex(SubscriptionProviderError, "schema rejected"):
            validate_prefetched_packet(self.job, changed)

        changed = copy.deepcopy(self.packet)
        changed["sources"][0]["exactExcerptUtf8Sha256"] = "0" * 64
        _rehash_packet(changed)
        with self.assertRaisesRegex(SubscriptionProviderError, "excerpt hash"):
            validate_prefetched_packet(self.job, changed)

        changed = copy.deepcopy(self.packet)
        changed["sources"][0]["publisher"] = "Wrong authority"
        _rehash_packet(changed)
        with self.assertRaisesRegex(SubscriptionProviderError, "publisher"):
            validate_prefetched_packet(self.job, changed)

        same_lane_job = copy.deepcopy(self.job)
        same_lane_job["officialAuthorities"].append(
            {
                "authorityId": "ca-on-other-lower-tier",
                "governmentLevel": "lower-tier",
                "publisher": "Other lower-tier authority",
                "domains": ["other.example.ca"],
            }
        )
        _rehash_job(same_lane_job)
        same_lane_packet = copy.deepcopy(self.packet)
        same_lane_packet["jobCanonicalSha256"] = same_lane_job[
            "jobCanonicalSha256"
        ]
        _rehash_packet(same_lane_packet)
        self.assertEqual(
            validate_prefetched_packet(
                same_lane_job,
                same_lane_packet,
            ),
            same_lane_packet,
        )

    def test_shared_domain_gap_trail_keeps_exact_authority_identity(self) -> None:
        changed_job = copy.deepcopy(self.job)
        shared_domain = changed_job["officialAuthorities"][0]["domains"][0]
        other_authority = {
            "authorityId": "ca-on-other-lower-tier",
            "governmentLevel": "lower-tier",
            "publisher": "Other lower-tier authority",
            "domains": [shared_domain],
        }
        changed_job["officialAuthorities"].append(other_authority)
        _rehash_job(changed_job)
        changed_packet = copy.deepcopy(self.packet)
        changed_packet["jobCanonicalSha256"] = changed_job[
            "jobCanonicalSha256"
        ]
        _rehash_packet(changed_packet)
        candidate = _candidate(
            changed_job,
            changed_packet,
            "anthropic",
            CLAUDE_MODEL,
        )
        candidate["gaps"][0]["reasonCode"] = "not-found"
        candidate["gaps"][0]["searchTrail"] = [
            {
                "authorityId": other_authority["authorityId"],
                "url": changed_packet["sources"][0]["url"],
            }
        ]
        with self.assertRaisesRegex(
            SubscriptionProviderError,
            "searchTrail authorityId does not match the gap authority",
        ):
            validate_candidate_packet_binding(
                changed_job,
                changed_packet,
                candidate,
            )

    @unittest.skipUnless(os.name == "nt", "Windows executable trust manifest")
    def test_live_executable_must_match_pinned_path_and_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            executable = base / ".local" / "bin" / "claude.exe"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"reviewed test executable")
            digest = hashlib.sha256(executable.read_bytes()).hexdigest()
            manifest = {
                "schemaVersion": (
                    "whatinthetax-trusted-provider-clis-1.0.0"
                ),
                "platform": "windows",
                "providers": {
                    "claude": {
                        "baseEnvironmentVariable": "USERPROFILE",
                        "relativePath": ".local/bin/claude.exe",
                        "version": "test",
                        "sha256": digest,
                        "publisher": "Test publisher",
                        "liveExecutionAllowed": True,
                    }
                },
            }
            manifest_path = base / "trusted-provider-clis.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            environment = {"USERPROFILE": str(base)}
            with patch(
                "national.subscription_provider_runner.TRUSTED_PROVIDER_CLI_PATH",
                manifest_path,
            ):
                _verify_trusted_executable(
                    "claude",
                    executable.resolve(),
                    environment,
                )
                executable.write_bytes(b"changed executable")
                with self.assertRaisesRegex(
                    SubscriptionProviderError,
                    "digest does not match",
                ):
                    _verify_trusted_executable(
                        "claude",
                        executable.resolve(),
                        environment,
                    )

    def test_sensitive_payload_is_rejected_before_any_cli_resolution(self) -> None:
        def forbidden_resolver(name: str, environ: object) -> Path:
            raise AssertionError(f"unexpected resolver call: {name} {environ}")

        def forbidden_runner(*args: object, **kwargs: object) -> BoundedProcessResult:
            raise AssertionError(f"unexpected process call: {args} {kwargs}")

        sensitive_excerpts = [
            ("credential", "Leaked sk-ant-" + "A" * 28),
            ("local path", r"Read C:\Users\resident\private.txt"),
            ("local path", r"Read \\server\share\private.txt"),
            ("local path", "Read ~/private.txt"),
            ("local path", "Read /tmp/private.txt"),
            ("email address", "Contact resident@example.ca"),
            ("phone-like", "Call +1 (519) 555-1234"),
            ("phone-like", "Call 5195551234"),
        ]
        for expected, excerpt in sensitive_excerpts:
            with self.subTest(expected=expected, excerpt=excerpt):
                changed_packet = copy.deepcopy(self.packet)
                changed_packet["sources"][0]["exactExcerpt"] = excerpt
                changed_packet["sources"][0][
                    "exactExcerptUtf8Sha256"
                ] = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
                _rehash_packet(changed_packet)
                with self.assertRaisesRegex(
                    SubscriptionProviderError,
                    expected,
                ):
                    run_subscription_provider(
                        self.job,
                        changed_packet,
                        provider="claude",
                        execute=True,
                        confirm_subscription_usage=True,
                        environ={},
                        process_runner=forbidden_runner,
                        executable_resolver=forbidden_resolver,
                        run_binding_at=RUN_BINDING_AT,
                    )

        changed_job = copy.deepcopy(self.job)
        changed_job["target"]["displayName"] = (
            "Municipality sk-ant-" + "B" * 28
        )
        _rehash_job(changed_job)
        changed_packet = copy.deepcopy(self.packet)
        changed_packet["jobCanonicalSha256"] = changed_job[
            "jobCanonicalSha256"
        ]
        _rehash_packet(changed_packet)
        with self.assertRaisesRegex(SubscriptionProviderError, "credential"):
            run_subscription_provider(
                changed_job,
                changed_packet,
                provider="claude",
                execute=True,
                confirm_subscription_usage=True,
                environ={},
                process_runner=forbidden_runner,
                executable_resolver=forbidden_resolver,
                run_binding_at=RUN_BINDING_AT,
            )

        with patch(
            "national.subscription_provider_runner.build_provider_prompt",
            return_value="Read /tmp/prompt-only.json",
        ):
            with self.assertRaisesRegex(
                SubscriptionProviderError,
                "local path.*prompt",
            ):
                run_subscription_provider(
                    self.job,
                    self.packet,
                    provider="claude",
                    execute=True,
                    confirm_subscription_usage=True,
                    environ={},
                    process_runner=forbidden_runner,
                    executable_resolver=forbidden_resolver,
                    run_binding_at=RUN_BINDING_AT,
                )

    def test_live_requires_both_explicit_flags_and_zero_retrieval_budget(self) -> None:
        with self.assertRaisesRegex(
            SubscriptionProviderError,
            "confirm-subscription-usage",
        ):
            run_subscription_provider(
                self.job,
                self.packet,
                provider="claude",
                execute=True,
                environ={},
                run_binding_at=RUN_BINDING_AT,
            )

        changed_job = copy.deepcopy(self.job)
        changed_job["budget"]["maxWebSearches"] = 1
        _rehash_job(changed_job)
        changed_packet = copy.deepcopy(self.packet)
        changed_packet["jobCanonicalSha256"] = changed_job["jobCanonicalSha256"]
        _rehash_packet(changed_packet)
        with self.assertRaisesRegex(SubscriptionProviderError, "maxWebSearches"):
            run_subscription_provider(
                changed_job,
                changed_packet,
                provider="claude",
                execute=True,
                confirm_subscription_usage=True,
                environ={},
                run_binding_at=RUN_BINDING_AT,
            )

        changed_job = copy.deepcopy(self.job)
        changed_job["budget"]["maxModelTurns"] = 2
        _rehash_job(changed_job)
        changed_packet = copy.deepcopy(self.packet)
        changed_packet["jobCanonicalSha256"] = changed_job["jobCanonicalSha256"]
        _rehash_packet(changed_packet)
        with self.assertRaisesRegex(SubscriptionProviderError, "maxModelTurns"):
            run_subscription_provider(
                changed_job,
                changed_packet,
                provider="claude",
                execute=True,
                confirm_subscription_usage=True,
                environ={},
                run_binding_at=RUN_BINDING_AT,
            )

    def test_claude_live_uses_one_closed_json_result_turn(self) -> None:
        candidate = _candidate(
            self.job,
            self.packet,
            "anthropic",
            CLAUDE_MODEL,
        )
        fake = FakeProviderProcess("claude", candidate)
        result = run_subscription_provider(
            self.job,
            self.packet,
            provider="claude",
            execute=True,
            confirm_subscription_usage=True,
            environ={"USERPROFILE": self.binary_directory.name},
            process_runner=fake,
            executable_resolver=self._resolver,
            executable_verifier=self._verifier,
            run_binding_at=RUN_BINDING_AT,
        )
        self.assertEqual(result, candidate)
        self.assertEqual(len(fake.calls), 4)
        final = fake.calls[-1]
        command = final["command"]
        self.assertIn("--tools", command)
        self.assertEqual(command[command.index("--tools") + 1], "")
        self.assertNotIn("--max-turns", command)
        self.assertIn("--permission-mode", command)
        self.assertIn("--no-session-persistence", command)
        self.assertIn("--safe-mode", command)
        self.assertEqual(
            command[command.index("--setting-sources") + 1],
            "",
        )
        self.assertEqual(
            command[command.index("--settings") + 1],
            _CLAUDE_INLINE_SETTINGS,
        )
        self.assertIn("--strict-mcp-config", command)
        self.assertEqual(
            command[command.index("--mcp-config") + 1],
            '{"mcpServers":{}}',
        )
        self.assertEqual(command.count("--output-format"), 1)
        self.assertEqual(
            command[command.index("--output-format") + 1],
            "json",
        )
        self.assertEqual(command.count("--system-prompt"), 1)
        self.assertEqual(
            command[command.index("--system-prompt") + 1],
            _CLAUDE_CLASSIFIER_SYSTEM_PROMPT,
        )
        self.assertNotIn("--json-schema", command)
        self.assertNotIn("--continue", command)
        self.assertNotIn("--resume", command)
        self.assertNotIn("--bare", command)
        self.assertNotIn("--fallback-model", command)
        self.assertGreater(len(final["input_bytes"]), 1_000)
        self.assertIn(b"Candidate JSON Schema:", final["input_bytes"])
        self.assertIn(b"Validated prefetched-source packet:", final["input_bytes"])
        self.assertIn(b'"runBindingAt"', final["input_bytes"])
        self.assertNotIn(b'"completedAt"', final["input_bytes"])
        working_directory = Path(final["cwd"])
        self.assertFalse(working_directory.exists())
        self.assertFalse(any(key.endswith("API_KEY") for key in final["env"]))

    def test_success_with_final_stderr_is_rejected(self) -> None:
        candidate = _candidate(
            self.job,
            self.packet,
            "anthropic",
            CLAUDE_MODEL,
        )

        class FinalStderrProcess(FakeProviderProcess):
            def __call__(
                self,
                command: list[str],
                **kwargs: object,
            ) -> BoundedProcessResult:
                result = super().__call__(command, **kwargs)
                if command[-1] not in {"--version", "--help", "status"}:
                    return BoundedProcessResult(
                        returncode=result.returncode,
                        stdout=result.stdout,
                        stderr=b"unexpected diagnostic",
                    )
                return result

        fake = FinalStderrProcess("claude", candidate)
        with self.assertRaisesRegex(
            SubscriptionProviderError,
            "unexpected stderr diagnostics",
        ):
            run_subscription_provider(
                self.job,
                self.packet,
                provider="claude",
                execute=True,
                confirm_subscription_usage=True,
                environ={},
                process_runner=fake,
                executable_resolver=self._resolver,
                executable_verifier=self._verifier,
                run_binding_at=RUN_BINDING_AT,
            )

    def test_candidate_run_binding_must_match_the_pre_run_binding(self) -> None:
        candidate = _candidate(
            self.job,
            self.packet,
            "anthropic",
            CLAUDE_MODEL,
        )
        candidate["producer"]["runBindingAt"] = "2026-07-27T12:00:01Z"
        fake = FakeProviderProcess("claude", candidate)
        with self.assertRaisesRegex(
            SubscriptionProviderError,
            "exact provider turn binding",
        ):
            run_subscription_provider(
                self.job,
                self.packet,
                provider="claude",
                execute=True,
                confirm_subscription_usage=True,
                environ={},
                process_runner=fake,
                executable_resolver=self._resolver,
                executable_verifier=self._verifier,
                run_binding_at=RUN_BINDING_AT,
            )
        self.assertEqual(len(fake.calls), 4)

    def test_claude_preflight_requires_settings_source_isolation(self) -> None:
        candidate = _candidate(
            self.job,
            self.packet,
            "anthropic",
            CLAUDE_MODEL,
        )

        class MissingSettingsIsolationProcess(FakeProviderProcess):
            def __call__(
                self,
                command: list[str],
                **kwargs: object,
            ) -> BoundedProcessResult:
                result = super().__call__(command, **kwargs)
                if command[-1] == "--help":
                    result = BoundedProcessResult(
                        returncode=result.returncode,
                        stdout=result.stdout.replace(
                            b"--setting-sources ",
                            b"",
                        ),
                        stderr=result.stderr,
                    )
                return result

        fake = MissingSettingsIsolationProcess("claude", candidate)
        with self.assertRaisesRegex(
            SubscriptionProviderError,
            "--setting-sources",
        ):
            run_subscription_provider(
                self.job,
                self.packet,
                provider="claude",
                execute=True,
                confirm_subscription_usage=True,
                environ={},
                process_runner=fake,
                executable_resolver=self._resolver,
                executable_verifier=self._verifier,
                run_binding_at=RUN_BINDING_AT,
            )
        self.assertEqual(len(fake.calls), 2)

    def test_agy_live_is_disabled_before_cli_resolution_or_invocation(self) -> None:
        candidate = _candidate(
            self.job,
            self.packet,
            "google-antigravity",
            AGY_MODEL,
        )
        fake = FakeProviderProcess("agy", candidate)
        with self.assertRaisesRegex(
            SubscriptionProviderError,
            "automatic Antigravity execution is disabled",
        ):
            run_subscription_provider(
                self.job,
                self.packet,
                provider="agy",
                execute=True,
                confirm_subscription_usage=True,
                environ={"USERPROFILE": self.binary_directory.name},
                process_runner=fake,
                executable_resolver=self._resolver,
                executable_verifier=self._verifier,
                run_binding_at=RUN_BINDING_AT,
            )
        self.assertEqual(fake.calls, [])

        dry_run = run_subscription_provider(
            self.job,
            self.packet,
            provider="agy",
            environ={},
            run_binding_at=RUN_BINDING_AT,
        )
        self.assertFalse(dry_run["liveEligible"])
        self.assertFalse(dry_run["automaticLiveExecutionSupported"])
        self.assertFalse(dry_run["requiresExecute"])
        self.assertFalse(dry_run["requiresSubscriptionUsageConfirmation"])
        self.assertIn(
            "automatic Antigravity execution is disabled",
            " ".join(dry_run["liveBlockers"]),
        )

    def test_outer_markdown_and_changed_packet_bindings_are_rejected(self) -> None:
        candidate = _candidate(
            self.job,
            self.packet,
            "anthropic",
            CLAUDE_MODEL,
        )
        fake = FakeProviderProcess("claude", candidate)
        fake.candidate_bytes = b"```json\n{}\n```"
        with self.assertRaisesRegex(
            SubscriptionProviderError,
            "strict JSON result envelope",
        ):
            run_subscription_provider(
                self.job,
                self.packet,
                provider="claude",
                execute=True,
                confirm_subscription_usage=True,
                environ={},
                process_runner=fake,
                executable_resolver=self._resolver,
                executable_verifier=self._verifier,
                run_binding_at=RUN_BINDING_AT,
            )

        mutations = {
            "retrievedAt": "2026-07-27T11:31:00Z",
            "contentType": "text/plain",
            "sourceContentSha256": "0" * 64,
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                changed = _candidate(
                    self.job,
                    self.packet,
                    "anthropic",
                    CLAUDE_MODEL,
                )
                changed["sources"][0][field] = value
                fake = FakeProviderProcess("claude", changed)
                with self.assertRaisesRegex(
                    SubscriptionProviderError,
                    "changed prefetched fields",
                ):
                    run_subscription_provider(
                        self.job,
                        self.packet,
                        provider="claude",
                        execute=True,
                        confirm_subscription_usage=True,
                        environ={},
                        process_runner=fake,
                        executable_resolver=self._resolver,
                        executable_verifier=self._verifier,
                        run_binding_at=RUN_BINDING_AT,
                    )

        changed = _candidate(
            self.job,
            self.packet,
            "anthropic",
            CLAUDE_MODEL,
        )
        changed["packetCanonicalSha256"] = "0" * 64
        fake = FakeProviderProcess("claude", changed)
        with self.assertRaisesRegex(
            SubscriptionProviderError,
            "packetCanonicalSha256 does not match",
        ):
            run_subscription_provider(
                self.job,
                self.packet,
                provider="claude",
                execute=True,
                confirm_subscription_usage=True,
                environ={},
                process_runner=fake,
                executable_resolver=self._resolver,
                executable_verifier=self._verifier,
                run_binding_at=RUN_BINDING_AT,
            )

    def test_every_packet_source_must_be_returned_exactly_once(self) -> None:
        two_source_packet = copy.deepcopy(self.packet)
        second = copy.deepcopy(two_source_packet["sources"][0])
        second["sourceKey"] = "S2"
        second["title"] = "2026 approved budget alternate notice"
        second["exactExcerpt"] = (
            "The approved 2026 budget is available for public review."
        )
        second["sourceContentSha256"] = hashlib.sha256(
            b"second-prefetched-source"
        ).hexdigest()
        second["exactExcerptUtf8Sha256"] = hashlib.sha256(
            second["exactExcerpt"].encode("utf-8")
        ).hexdigest()
        two_source_packet["sources"].append(second)
        _rehash_packet(two_source_packet)
        self.trusted_packet_digest = two_source_packet["packetCanonicalSha256"]

        reversed_candidate = _candidate(
            self.job,
            two_source_packet,
            "anthropic",
            CLAUDE_MODEL,
        )
        reversed_candidate["sources"].reverse()
        fake = FakeProviderProcess("claude", reversed_candidate)
        self.assertEqual(
            run_subscription_provider(
                self.job,
                two_source_packet,
                provider="claude",
                execute=True,
                confirm_subscription_usage=True,
                environ={},
                process_runner=fake,
                executable_resolver=self._resolver,
                executable_verifier=self._verifier,
                run_binding_at=RUN_BINDING_AT,
            ),
            reversed_candidate,
        )

        omitted = _candidate(
            self.job,
            two_source_packet,
            "anthropic",
            CLAUDE_MODEL,
        )
        omitted["sources"].pop()
        fake = FakeProviderProcess("claude", omitted)
        with self.assertRaisesRegex(
            SubscriptionProviderError,
            "every packet source exactly once",
        ):
            run_subscription_provider(
                self.job,
                two_source_packet,
                provider="claude",
                execute=True,
                confirm_subscription_usage=True,
                environ={},
                process_runner=fake,
                executable_resolver=self._resolver,
                executable_verifier=self._verifier,
                run_binding_at=RUN_BINDING_AT,
            )

        duplicated = _candidate(
            self.job,
            two_source_packet,
            "anthropic",
            CLAUDE_MODEL,
        )
        duplicated["sources"][1] = copy.deepcopy(duplicated["sources"][0])
        fake = FakeProviderProcess("claude", duplicated)
        with self.assertRaisesRegex(
            SubscriptionProviderError,
            "duplicate sourceKey",
        ):
            run_subscription_provider(
                self.job,
                two_source_packet,
                provider="claude",
                execute=True,
                confirm_subscription_usage=True,
                environ={},
                process_runner=fake,
                executable_resolver=self._resolver,
                executable_verifier=self._verifier,
                run_binding_at=RUN_BINDING_AT,
            )

        extra = _candidate(
            self.job,
            self.packet,
            "anthropic",
            CLAUDE_MODEL,
        )
        self.trusted_packet_digest = self.packet["packetCanonicalSha256"]
        extra_source = copy.deepcopy(extra["sources"][0])
        extra_source["sourceKey"] = "S2"
        extra["sources"].append(extra_source)
        fake = FakeProviderProcess("claude", extra)
        with self.assertRaisesRegex(
            SubscriptionProviderError,
            "every packet source exactly once",
        ):
            run_subscription_provider(
                self.job,
                self.packet,
                provider="claude",
                execute=True,
                confirm_subscription_usage=True,
                environ={},
                process_runner=fake,
                executable_resolver=self._resolver,
                executable_verifier=self._verifier,
                run_binding_at=RUN_BINDING_AT,
            )

    def test_candidate_authority_id_is_exact_within_a_shared_lane(self) -> None:
        changed_job = copy.deepcopy(self.job)
        other_authority = {
            "authorityId": "ca-on-other-lower-tier",
            "governmentLevel": "lower-tier",
            "publisher": "Other lower-tier authority",
            "domains": ["other.example.ca"],
        }
        changed_job["officialAuthorities"].append(other_authority)
        changed_job["requestedDocuments"].append(
            {
                "documentType": "approved-budget",
                "authorityId": other_authority["authorityId"],
                "governmentLevel": "lower-tier",
                "fiscalYear": 2026,
                "required": False,
            }
        )
        _rehash_job(changed_job)
        changed_packet = copy.deepcopy(self.packet)
        changed_packet["jobCanonicalSha256"] = changed_job[
            "jobCanonicalSha256"
        ]
        _rehash_packet(changed_packet)
        self.trusted_packet_digest = changed_packet["packetCanonicalSha256"]

        candidate = _candidate(
            changed_job,
            changed_packet,
            "anthropic",
            CLAUDE_MODEL,
        )
        source = candidate["sources"][0]
        original_authority_id = source["authorityId"]
        source["authorityId"] = other_authority["authorityId"]
        source["publisher"] = other_authority["publisher"]
        source["url"] = "https://other.example.ca/budget"
        candidate["gaps"].append(
            {
                "documentType": source["documentType"],
                "authorityId": original_authority_id,
                "governmentLevel": source["governmentLevel"],
                "fiscalYear": source["fiscalYear"],
                "reasonCode": "not-yet-researched",
                "searchTrail": [],
                "note": "No supplied excerpt supports this required document.",
            }
        )
        fake = FakeProviderProcess("claude", candidate)
        with self.assertRaisesRegex(
            SubscriptionProviderError,
            "changed prefetched fields.*authorityId",
        ):
            run_subscription_provider(
                changed_job,
                changed_packet,
                provider="claude",
                execute=True,
                confirm_subscription_usage=True,
                environ={},
                process_runner=fake,
                executable_resolver=self._resolver,
                executable_verifier=self._verifier,
                run_binding_at=RUN_BINDING_AT,
            )

    def test_claude_arbitrary_wrappers_and_error_results_are_rejected(self) -> None:
        candidate = _candidate(
            self.job,
            self.packet,
            "anthropic",
            CLAUDE_MODEL,
        )
        wrapped = _claude_result(candidate)
        wrapped["result"] = canonical_json_bytes(
            {"output": candidate}
        ).decode("utf-8")
        fenced = _claude_result(candidate)
        fenced["result"] = (
            "```json\n"
            + canonical_json_bytes(candidate).decode("utf-8")
            + "\n```"
        )
        concatenated = _claude_result(candidate)
        concatenated["result"] = (
            canonical_json_bytes(candidate).decode("utf-8") + "{}"
        )
        object_result = _claude_result(candidate)
        object_result["result"] = candidate
        duplicate_candidate_key = _claude_result(candidate)
        candidate_text = canonical_json_bytes(candidate).decode("utf-8")
        duplicate_candidate_key["result"] = (
            '{"schemaVersion":"duplicate",'
            + candidate_text[1:]
        )
        float_candidate = _claude_result(candidate)
        float_candidate["result"] = candidate_text.replace(
            '"fiscalYear":2026',
            '"fiscalYear":2026.0',
            1,
        )
        unexpected_structured = _claude_result(candidate)
        unexpected_structured["structured_output"] = candidate
        invalid_outputs = [
            canonical_json_bytes(candidate),
            canonical_json_bytes(wrapped),
            canonical_json_bytes(fenced),
            canonical_json_bytes(concatenated),
            canonical_json_bytes(object_result),
            canonical_json_bytes(duplicate_candidate_key),
            canonical_json_bytes(float_candidate),
            canonical_json_bytes(unexpected_structured),
            b'{"type":"result","type":"result"}',
        ]
        for invalid in invalid_outputs:
            with self.subTest(invalid=invalid[:60]):
                fake = FakeProviderProcess("claude", candidate)
                fake.candidate_bytes = invalid
                with self.assertRaises(SubscriptionProviderError):
                    run_subscription_provider(
                        self.job,
                        self.packet,
                        provider="claude",
                        execute=True,
                        confirm_subscription_usage=True,
                        environ={},
                        process_runner=fake,
                        executable_resolver=self._resolver,
                        executable_verifier=self._verifier,
                        run_binding_at=RUN_BINDING_AT,
                    )
                self.assertEqual(len(fake.calls), 4)

        error_result = _claude_result(candidate)
        error_result["subtype"] = "error_during_execution"
        error_result["is_error"] = True
        fake = FakeProviderProcess("claude", candidate)
        fake.candidate_bytes = canonical_json_bytes(error_result)
        with self.assertRaisesRegex(
            SubscriptionProviderError,
            "error-free success",
        ):
            run_subscription_provider(
                self.job,
                self.packet,
                provider="claude",
                execute=True,
                confirm_subscription_usage=True,
                environ={},
                process_runner=fake,
                executable_resolver=self._resolver,
                executable_verifier=self._verifier,
                run_binding_at=RUN_BINDING_AT,
            )
        self.assertEqual(len(fake.calls), 4)

    def test_claude_result_envelope_is_one_turn_and_no_tool_closed(self) -> None:
        candidate = _candidate(
            self.job,
            self.packet,
            "anthropic",
            CLAUDE_MODEL,
        )
        mutations = [
            ("num_turns", 0, "exactly one model turn"),
            ("num_turns", 2, "exactly one model turn"),
            ("result", "", "non-empty candidate JSON string"),
            ("result", "commentary", "raw strict JSON candidate"),
            (
                "permission_denials",
                [{"tool_name": "Read"}],
                "permission denials",
            ),
            ("deferred_tool_use", None, "deferred tool use"),
            ("deferred_tool_use", {}, "deferred tool use"),
            ("stop_reason", "tool_use", "no-tool end_turn"),
            ("stop_reason", "max_tokens", "no-tool end_turn"),
            ("api_error_status", 500, "API error"),
            ("unreviewed", True, "unreviewed fields"),
        ]
        for field, value, message in mutations:
            with self.subTest(field=field):
                envelope = _claude_result(candidate)
                envelope[field] = value
                fake = FakeProviderProcess("claude", candidate)
                fake.candidate_bytes = canonical_json_bytes(envelope)
                with self.assertRaisesRegex(
                    SubscriptionProviderError,
                    message,
                ):
                    run_subscription_provider(
                        self.job,
                        self.packet,
                        provider="claude",
                        execute=True,
                        confirm_subscription_usage=True,
                        environ={},
                        process_runner=fake,
                        executable_resolver=self._resolver,
                        executable_verifier=self._verifier,
                        run_binding_at=RUN_BINDING_AT,
                    )
                self.assertEqual(len(fake.calls), 4)

        envelope = _claude_result(candidate)
        fake = FakeProviderProcess("claude", candidate)
        encoded = json.dumps(envelope, separators=(",", ":"))
        fake.candidate_bytes = encoded.replace(
            '"total_cost_usd":0.0125',
            '"total_cost_usd":NaN',
        ).encode()
        with self.assertRaisesRegex(
            SubscriptionProviderError,
            "non-finite number",
        ):
            run_subscription_provider(
                self.job,
                self.packet,
                provider="claude",
                execute=True,
                confirm_subscription_usage=True,
                environ={},
                process_runner=fake,
                executable_resolver=self._resolver,
                executable_verifier=self._verifier,
                run_binding_at=RUN_BINDING_AT,
            )
        self.assertEqual(len(fake.calls), 4)

    def test_claude_usage_is_exact_model_finite_and_budget_bound(self) -> None:
        candidate = _candidate(
            self.job,
            self.packet,
            "anthropic",
            CLAUDE_MODEL,
        )
        invalid: list[tuple[str, dict, str]] = []

        envelope = _claude_result(candidate)
        usage = envelope["modelUsage"].pop(CLAUDE_MODEL)
        envelope["modelUsage"]["claude-unrequested"] = usage
        invalid.append(("wrong model", envelope, "only the requested model"))

        envelope = _claude_result(candidate)
        envelope["modelUsage"]["claude-fallback"] = copy.deepcopy(
            envelope["modelUsage"][CLAUDE_MODEL]
        )
        invalid.append(("fallback model", envelope, "only the requested model"))

        envelope = _claude_result(candidate)
        envelope["modelUsage"][CLAUDE_MODEL] = "not-an-object"
        invalid.append(("model usage type", envelope, "must be an object"))

        envelope = _claude_result(candidate)
        del envelope["usage"]["output_tokens"]
        invalid.append(
            ("missing aggregate output", envelope, "non-negative integer")
        )

        envelope = _claude_result(candidate)
        del envelope["modelUsage"][CLAUDE_MODEL]["outputTokens"]
        invalid.append(("missing model output", envelope, "non-negative integer"))

        envelope = _claude_result(candidate)
        envelope["usage"]["output_tokens"] = True
        invalid.append(("boolean output", envelope, "non-negative integer"))

        envelope = _claude_result(candidate)
        envelope["usage"]["output_tokens"] = 450.0
        invalid.append(("fractional output", envelope, "non-negative integer"))

        envelope = _claude_result(candidate)
        envelope["usage"]["input_tokens"] = -1
        invalid.append(
            ("negative usage", envelope, "non-negative finite number")
        )

        envelope = _claude_result(candidate)
        envelope["usage"]["output_tokens"] = (
            self.job["budget"]["maxOutputTokens"] + 1
        )
        invalid.append(("aggregate over budget", envelope, "token ceiling"))

        envelope = _claude_result(candidate)
        envelope["modelUsage"][CLAUDE_MODEL]["outputTokens"] = (
            self.job["budget"]["maxOutputTokens"] + 1
        )
        invalid.append(("model over budget", envelope, "token ceiling"))

        envelope = _claude_result(candidate)
        envelope["modelUsage"][CLAUDE_MODEL]["outputTokens"] = 449
        invalid.append(("usage mismatch", envelope, "internally inconsistent"))

        envelope = _claude_result(candidate)
        envelope["modelUsage"][CLAUDE_MODEL]["costUSD"] = float("nan")
        invalid.append(("nested NaN", envelope, "non-finite number"))

        envelope = _claude_result(candidate)
        envelope["usage"]["input_tokens"] = float("inf")
        invalid.append(("nested infinity", envelope, "non-finite number"))

        for label, envelope, message in invalid:
            with self.subTest(label=label):
                fake = FakeProviderProcess("claude", candidate)
                fake.candidate_bytes = json.dumps(
                    envelope,
                    separators=(",", ":"),
                ).encode("utf-8")
                with self.assertRaisesRegex(
                    SubscriptionProviderError,
                    message,
                ):
                    run_subscription_provider(
                        self.job,
                        self.packet,
                        provider="claude",
                        execute=True,
                        confirm_subscription_usage=True,
                        environ={},
                        process_runner=fake,
                        executable_resolver=self._resolver,
                        executable_verifier=self._verifier,
                        run_binding_at=RUN_BINDING_AT,
                    )
                self.assertEqual(len(fake.calls), 4)

    def test_mock_runner_cannot_bypass_hard_output_limit(self) -> None:
        candidate = _candidate(
            self.job,
            self.packet,
            "anthropic",
            CLAUDE_MODEL,
        )
        fake = FakeProviderProcess("claude", candidate)
        fake.candidate_bytes = b"x" * (MAX_STDOUT_UTF8_BYTES + 1)
        with self.assertRaisesRegex(SubscriptionProviderError, "hard byte limit"):
            run_subscription_provider(
                self.job,
                self.packet,
                provider="claude",
                execute=True,
                confirm_subscription_usage=True,
                environ={},
                process_runner=fake,
                executable_resolver=self._resolver,
                executable_verifier=self._verifier,
                run_binding_at=RUN_BINDING_AT,
            )


if __name__ == "__main__":
    unittest.main()
