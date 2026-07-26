from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from jsonschema import Draft202012Validator, ValidationError

from national.ai_gaps import (
    AIGapPolicy,
    BoundedExcerpt,
    DeterministicGap,
    build_ai_gap_packet,
    build_ai_gap_queue,
)
from national.cache import ContentAddressedSourceCache
from national.models import canonical_sha256
from national.subscription_worker import (
    MAX_STRICT_JSON_DEPTH,
    SubscriptionRunFailure,
    SubscriptionWorkerError,
    assert_local_operator_environment,
    assert_subscription_environment,
    authorize_subscription_packet,
    build_candidate_envelope,
    build_codex_exec_command,
    build_model_output_schema,
    build_prompt,
    claim_subscription_attempt,
    finish_subscription_attempt,
    load_ai_gap_policy,
    load_trusted_codex_lock,
    parse_strict_json,
    reject_tool_events,
    run_subscription_packet,
    validate_ai_gap_queue,
    validate_candidate_schema,
    validate_subscription_packet,
    verify_trusted_codex_installation,
    verify_model_output,
)
from scripts import run_subscription_gap_review as review_cli


class SubscriptionCodexWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cache = ContentAddressedSourceCache(self.root / "cache")
        self.snapshot = self.cache.store(
            source_id="oshawa-2026-tax-bylaw",
            payload=b"%PDF-locked-official-source",
            media_type="application/pdf",
            request_url="https://www.oshawa.ca/tax-bylaw.pdf",
        )
        self.excerpt_text = "Residential tax class | General rate | 0.012345"
        self.document = (
            "Official by-law heading\n"
            + self.excerpt_text
            + "\nCertification and signatures"
        )
        normalized = self.cache.store_normalized_text(
            source_snapshot=self.snapshot,
            normalized_text=self.document,
            normalizer_id="auditback-pdf-text",
            normalizer_version="1.0.0",
        )
        excerpt_start = self.document.index(self.excerpt_text)
        excerpt = BoundedExcerpt.from_document(
            self.document,
            start_char=excerpt_start,
            end_char=excerpt_start + len(self.excerpt_text),
            locator="page 4, table 2, row Residential",
        )
        gap = DeterministicGap(
            gap_id="oshawa-2026-tax-rate",
            entity_id="ca:gov:on:municipal:3518013",
            gap_code="table-layout-not-supported",
            requested_fields=("residentialTaxRate",),
            source_id=self.snapshot.source_id,
            source_sha256=self.snapshot.sha256,
            normalized_text_sha256=normalized.normalized_text_sha256,
            deterministic_attempts=(
                "structured API lookup: no endpoint published",
                "PDF table parser: merged header cells unsupported",
            ),
        )
        self.policy = AIGapPolicy(enabled=True)
        self.packet = build_ai_gap_packet(
            gap,
            [excerpt],
            policy=self.policy,
            explicit_opt_in=True,
            normalized_text_resolver=self.cache,
        )
        self.queue = build_ai_gap_queue(
            [self.packet],
            policy=self.policy,
            normalized_text_resolver=self.cache,
        )
        self.queue_hash = self.queue["queueCanonicalSha256"]
        self.queue_schema = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "national"
                / "schemas"
                / "ai-gap-queue.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.authorization = validate_subscription_packet(
            self.queue,
            self.packet["packetCanonicalSha256"],
            policy=self.policy,
            normalized_text_resolver=self.cache,
            queue_schema=self.queue_schema,
        )
        self.prompt = build_prompt(
            self.packet,
            queue_canonical_sha256=self.queue_hash,
        )
        self.prompt_hash = hashlib.sha256(self.prompt.encode("utf-8")).hexdigest()
        self.output_schema = build_model_output_schema(
            self.packet,
            prompt_canonical_sha256=self.prompt_hash,
        )

    def _candidate_output(self) -> dict:
        value = "0.012345"
        quote_start = self.excerpt_text.index(value)
        quote_end = quote_start + len(value)
        schema_version = self.output_schema["properties"]["schemaVersion"]["enum"][0]
        return {
            "schemaVersion": schema_version,
            "packetCanonicalSha256": self.packet["packetCanonicalSha256"],
            "promptCanonicalSha256": self.prompt_hash,
            "fieldDecisions": [
                {
                    "requestedField": "residentialTaxRate",
                    "status": "candidate",
                    "valueText": value,
                    "evidenceSpans": [
                        {
                            "excerptIndex": 0,
                            "quoteStart": quote_start,
                            "quoteEnd": quote_end,
                            "exactQuote": value,
                            "excerptTextSha256": self.packet["excerpts"][0][
                                "excerptTextSha256"
                            ],
                        }
                    ],
                    "secondCheckRequired": True,
                }
            ],
        }

    def _enabled_policy_contract(self, suffix: str) -> tuple[Path, Path]:
        policy_document = parse_strict_json(
            (
                Path(__file__).resolve().parents[1]
                / "national"
                / "ai_gap_policy.json"
            ).read_bytes()
        )
        policy_document["enabled"] = True
        policy_path = self.root / f"enabled-policy-{suffix}.json"
        queue_schema_path = self.root / f"queue-schema-{suffix}.json"
        policy_path.write_text(
            json.dumps(policy_document),
            encoding="utf-8",
        )
        queue_schema_path.write_text(
            json.dumps(self.queue_schema),
            encoding="utf-8",
        )
        return policy_path, queue_schema_path

    def test_requires_exact_chatgpt_subscription_login(self) -> None:
        assert_subscription_environment(
            login_status="Logged in using ChatGPT",
            environ={},
        )

        for other_status in (
            "Logged in using an API key",
            "Logged in using ChatGPT and API key",
            "Not logged in",
            "",
        ):
            with self.subTest(login_status=other_status):
                with self.assertRaises(SubscriptionWorkerError):
                    assert_subscription_environment(
                        login_status=other_status,
                        environ={},
                    )

    def test_rejects_api_credentials_and_provider_overrides(self) -> None:
        forbidden = (
            "OPENAI_API_KEY",
            "CODEX_API_KEY",
            "CODEX_ACCESS_TOKEN",
            "OPENAI_BASE_URL",
            "OPENAI_API_BASE",
            "AZURE_OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "GOOGLE_API_KEY",
        )
        for variable in forbidden:
            with self.subTest(variable=variable):
                with self.assertRaises(SubscriptionWorkerError):
                    assert_subscription_environment(
                        login_status="Logged in using ChatGPT",
                        environ={variable: "must-not-be-used"},
                    )

        # Merely declared but empty variables cannot route or authenticate a call.
        assert_subscription_environment(
            login_status="Logged in using ChatGPT",
            environ={name: "" for name in forbidden},
        )
        for variable in ("CI", "GITHUB_ACTIONS", "TF_BUILD"):
            with self.subTest(automation_variable=variable):
                with self.assertRaises(SubscriptionWorkerError):
                    assert_subscription_environment(
                        login_status="Logged in using ChatGPT",
                        environ={variable: "true"},
                    )
        with self.assertRaises(SubscriptionWorkerError):
            assert_local_operator_environment(
                environ={"CODEX_HOME": "C:/copied-auth"}
            )

    @unittest.skipUnless(os.name == "nt", "pinned worker is Windows-only")
    def test_signature_verifier_ignores_poisoned_windows_path_environment(
        self,
    ) -> None:
        trusted_windows = self.root / "trusted-windows"
        trusted_system = trusted_windows / "System32"
        trusted_modules = (
            trusted_system
            / "WindowsPowerShell"
            / "v1.0"
            / "Modules"
        )
        trusted_modules.mkdir(parents=True)
        trusted_powershell = trusted_modules.parent / "powershell.exe"
        trusted_powershell.write_bytes(b"trusted-system-powershell")
        trusted_program_files = self.root / "trusted-program-files"
        trusted_profile = self.root / "trusted-profile"
        trusted_local_app_data = self.root / "trusted-local-app-data"
        trusted_roaming_app_data = self.root / "trusted-roaming-app-data"
        trusted_program_files.mkdir()
        trusted_profile.mkdir()
        (trusted_local_app_data / "Temp").mkdir(parents=True)
        trusted_roaming_app_data.mkdir()
        codex_executable = self.root / "trusted-codex.exe"
        codex_executable.write_bytes(b"signed-codex")

        attacker_root = self.root / "attacker-windows"
        attacker_powershell = (
            attacker_root
            / "System32"
            / "WindowsPowerShell"
            / "v1.0"
            / "powershell.exe"
        )
        attacker_powershell.parent.mkdir(parents=True)
        attacker_powershell.write_bytes(b"attacker")
        attacker_program_files = self.root / "attacker-program-files"
        attacker_program_files.mkdir()
        poison = {
            "PATH": str(attacker_program_files),
            "sYsTeMrOoT": str(attacker_root),
            "WINDIR": str(attacker_root),
            "ProgramFiles": str(attacker_program_files),
            "PROGRAMW6432": str(attacker_program_files),
            "ProgramFiles(x86)": str(attacker_program_files),
            "PSModulePath": str(attacker_program_files),
            "userprofile": str(attacker_program_files),
            "localappdata": str(attacker_program_files),
            "temp": str(attacker_program_files),
        }
        lock = {
            "codexCliVersion": "codex-cli 0.144.4",
            "executableSha256": "a" * 64,
            "authenticodePublisher": "CN=OpenAI Test",
        }
        signature_result = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "status": "Valid",
                    "subject": lock["authenticodePublisher"],
                }
            ),
            stderr="",
        )
        runner = Mock(return_value=signature_result)

        def known_folder(csidl: int, *, label: str) -> Path:
            del label
            if csidl == 0x0028:
                return trusted_profile
            if csidl == 0x0026:
                return trusted_program_files
            if csidl == 0x001C:
                return trusted_local_app_data
            if csidl == 0x001A:
                return trusted_roaming_app_data
            raise AssertionError(f"unexpected CSIDL: {csidl}")

        with (
            patch(
                "national.subscription_worker.shutil.which",
                return_value=str(codex_executable),
            ),
            patch(
                "national.subscription_worker.load_trusted_codex_lock",
                return_value=lock,
            ),
            patch(
                "national.subscription_worker._sha256_file",
                return_value=lock["executableSha256"],
            ),
            patch(
                "national.subscription_worker._windows_directory",
                return_value=trusted_windows,
            ),
            patch(
                "national.subscription_worker._windows_system_directory",
                return_value=trusted_system,
            ),
            patch(
                "national.subscription_worker._windows_known_folder",
                side_effect=known_folder,
            ),
        ):
            resolved, _ = verify_trusted_codex_installation(
                runner=runner,
                environ=poison,
            )

        self.assertEqual(resolved, codex_executable)
        command = runner.call_args.args[0]
        child_environment = runner.call_args.kwargs["env"]
        self.assertEqual(Path(command[0]), trusted_powershell)
        self.assertEqual(
            child_environment["SystemRoot"],
            str(trusted_windows),
        )
        self.assertEqual(child_environment["WINDIR"], str(trusted_windows))
        self.assertEqual(
            child_environment["ProgramFiles"],
            str(trusted_program_files),
        )
        self.assertEqual(
            child_environment["PSModulePath"],
            str(trusted_modules),
        )
        self.assertEqual(
            child_environment["PATH"],
            str(trusted_system),
        )
        self.assertEqual(
            child_environment["USERPROFILE"],
            str(trusted_profile),
        )
        self.assertEqual(
            child_environment["LOCALAPPDATA"],
            str(trusted_local_app_data),
        )
        self.assertEqual(
            child_environment["TEMP"],
            str(trusted_local_app_data / "Temp"),
        )
        self.assertNotIn(str(attacker_root), child_environment.values())
        self.assertNotIn(str(attacker_program_files), child_environment.values())

    def test_strict_json_rejects_duplicate_keys_and_non_finite_numbers(self) -> None:
        for payload in (
            '{"fieldDecisions":[],"fieldDecisions":[{"status":"candidate"}]}',
            '{"quoteStart":NaN}',
            '{"quoteEnd":Infinity}',
            '{"excerptIndex":-Infinity}',
            '{"oversizedInteger":' + ("9" * 5_000) + "}",
            ("[" * 1_200) + "0" + ("]" * 1_200),
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(SubscriptionWorkerError):
                    parse_strict_json(payload)

    def test_strict_json_enforces_a_runtime_independent_nesting_limit(self) -> None:
        within_limit = (
            ("[" * MAX_STRICT_JSON_DEPTH)
            + "0"
            + ("]" * MAX_STRICT_JSON_DEPTH)
        )
        beyond_limit = (
            ("[" * (MAX_STRICT_JSON_DEPTH + 1))
            + "0"
            + ("]" * (MAX_STRICT_JSON_DEPTH + 1))
        )

        self.assertIsInstance(parse_strict_json(within_limit), list)
        with self.assertRaises(SubscriptionWorkerError):
            parse_strict_json(beyond_limit)

    def test_codex_command_is_locked_to_safe_subscription_execution(self) -> None:
        job_directory = self.root / "empty-job"
        job_directory.mkdir()
        schema_path = job_directory / "model-output.schema.json"
        message_path = job_directory / "last-message.json"
        command = build_codex_exec_command(
            codex_path="codex",
            model="gpt-5.4-mini",
            working_directory=job_directory,
            output_schema_path=schema_path,
            last_message_path=message_path,
        )

        self.assertEqual(command[0], "codex")
        self.assertIn("exec", command)
        self.assertLess(command.index("--ask-for-approval"), command.index("exec"))
        approval_index = command.index("--ask-for-approval")
        self.assertEqual(command[approval_index + 1], "never")
        for required in (
            "--strict-config",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            "--model",
            "--output-schema",
            "--output-last-message",
            "--json",
        ):
            self.assertIn(required, command)
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertEqual(command[command.index("--model") + 1], "gpt-5.4-mini")
        self.assertEqual(command[-1], "-")

        rendered = " ".join(str(item) for item in command)
        for disabled_capability in (
            "shell_tool",
            "apps",
            "hooks",
            "multi_agent",
            "remote_plugin",
            "fast_mode",
        ):
            self.assertRegex(
                rendered,
                rf"(?:--disable {disabled_capability}|"
                rf"features\.{disabled_capability}=false)",
            )
        self.assertRegex(rendered, r'web_search=(?:\\"|")?disabled')
        for dangerous in (
            "--yolo",
            "--dangerously-bypass-approvals-and-sandbox",
            "--add-dir",
            "danger-full-access",
            "workspace-write",
            " resume ",
            "--oss",
            "--local-provider",
        ):
            self.assertNotIn(dangerous, f" {rendered} ")

    def test_prompt_and_hash_are_deterministic_and_packet_bound(self) -> None:
        repeated = build_prompt(
            self.packet,
            queue_canonical_sha256=self.queue_hash,
        )
        self.assertEqual(repeated, self.prompt)
        self.assertEqual(
            hashlib.sha256(repeated.encode("utf-8")).hexdigest(),
            self.prompt_hash,
        )
        self.assertIn(self.packet["packetCanonicalSha256"], repeated)
        self.assertIn(self.queue_hash, repeated)
        self.assertIn(self.excerpt_text, repeated)
        self.assertNotIn(self.snapshot.request_url, repeated)

        changed_queue_hash = "f" * 64
        changed = build_prompt(
            self.packet,
            queue_canonical_sha256=changed_queue_hash,
        )
        self.assertNotEqual(changed, repeated)
        self.assertNotEqual(
            hashlib.sha256(changed.encode("utf-8")).hexdigest(),
            self.prompt_hash,
        )

    def test_output_schema_is_closed_and_binds_packet_and_prompt(self) -> None:
        Draft202012Validator.check_schema(self.output_schema)
        self.assertFalse(self.output_schema["additionalProperties"])
        properties = self.output_schema["properties"]
        self.assertEqual(
            properties["packetCanonicalSha256"]["enum"],
            [self.packet["packetCanonicalSha256"]],
        )
        self.assertEqual(
            properties["promptCanonicalSha256"]["enum"],
            [self.prompt_hash],
        )

        forbidden_provider_keywords = {
            "$schema",
            "const",
            "prefixItems",
            "uniqueItems",
            "allOf",
            "if",
            "then",
            "else",
            "not",
        }

        def assert_provider_subset(value: object) -> None:
            if isinstance(value, dict):
                self.assertFalse(
                    forbidden_provider_keywords.intersection(value),
                    value,
                )
                if value.get("type") == "object":
                    self.assertFalse(value["additionalProperties"])
                    self.assertEqual(
                        set(value["required"]),
                        set(value["properties"]),
                    )
                if value.get("type") == "array":
                    self.assertIsInstance(value.get("items"), dict)
                for nested in value.values():
                    assert_provider_subset(nested)
            elif isinstance(value, list):
                for nested in value:
                    assert_provider_subset(nested)

        assert_provider_subset(self.output_schema)
        self.assertEqual(
            properties["packetCanonicalSha256"]["enum"][0],
            self.packet["packetCanonicalSha256"],
        )

        valid = self._candidate_output()
        Draft202012Validator(self.output_schema).validate(valid)
        with self.assertRaises(ValidationError):
            Draft202012Validator(self.output_schema).validate(
                {**valid, "unrequestedNarrative": "looks plausible"}
            )

    def test_verifier_requires_exact_quote_offsets_and_value_text(self) -> None:
        valid = self._candidate_output()
        self.assertEqual(
            verify_model_output(
                self.packet,
                valid,
                prompt_canonical_sha256=self.prompt_hash,
            ),
            valid,
        )

        bad_quote = {
            **valid,
            "fieldDecisions": [
                {
                    **valid["fieldDecisions"][0],
                    "evidenceSpans": [
                        {
                            **valid["fieldDecisions"][0]["evidenceSpans"][0],
                            "quoteEnd": valid["fieldDecisions"][0]["evidenceSpans"][0][
                                "quoteEnd"
                            ]
                            - 1,
                        }
                    ],
                }
            ],
        }
        with self.assertRaises(SubscriptionWorkerError):
            verify_model_output(
                self.packet,
                bad_quote,
                prompt_canonical_sha256=self.prompt_hash,
            )

        invented_value = {
            **valid,
            "fieldDecisions": [
                {
                    **valid["fieldDecisions"][0],
                    "valueText": "0.999999",
                }
            ],
        }
        with self.assertRaises(SubscriptionWorkerError):
            verify_model_output(
                self.packet,
                invented_value,
                prompt_canonical_sha256=self.prompt_hash,
            )

        one_sided_conflict = {
            **valid,
            "fieldDecisions": [
                {
                    **valid["fieldDecisions"][0],
                    "status": "conflict",
                    "valueText": None,
                }
            ],
        }
        with self.assertRaises(SubscriptionWorkerError):
            verify_model_output(
                self.packet,
                one_sided_conflict,
                prompt_canonical_sha256=self.prompt_hash,
            )

    def test_verifier_rejects_replayed_packet_or_prompt_output(self) -> None:
        valid = self._candidate_output()
        for replay in (
            {**valid, "packetCanonicalSha256": "f" * 64},
            {**valid, "promptCanonicalSha256": "e" * 64},
        ):
            with self.subTest(replay=replay):
                with self.assertRaises(SubscriptionWorkerError):
                    verify_model_output(
                        self.packet,
                        replay,
                        prompt_canonical_sha256=self.prompt_hash,
                    )

    def test_any_tool_activity_quarantines_the_model_result(self) -> None:
        reject_tool_events(
            [
                {"type": "thread.started", "thread_id": "local"},
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "{}"},
                },
            ]
        )

        tool_events = (
            {
                "type": "item.started",
                "item": {"type": "command_execution", "command": "dir"},
            },
            {
                "type": "item.completed",
                "item": {"type": "web_search", "query": "municipal rate"},
            },
            {"type": "tool_call", "name": "read_file", "arguments": {}},
            {"type": "subagent.started", "agent": "helper"},
        )
        for event in tool_events:
            with self.subTest(event=event):
                with self.assertRaises(SubscriptionWorkerError):
                    reject_tool_events([event])

        with self.assertRaises(SubscriptionWorkerError):
            reject_tool_events(
                [{"type": "turn.future-progress", "message": "unknown event"}]
            )

    def test_queue_must_be_enabled_and_match_a_fresh_locked_source_rebuild(self) -> None:
        queue_schema = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "national"
                / "schemas"
                / "ai-gap-queue.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            validate_ai_gap_queue(
                self.queue,
                policy=self.policy,
                normalized_text_resolver=self.cache,
                queue_schema=queue_schema,
            ),
            self.queue,
        )

        checked_in_policy_document = parse_strict_json(
            (
                Path(__file__).resolve().parents[1]
                / "national"
                / "ai_gap_policy.json"
            ).read_bytes()
        )
        disabled_policy = load_ai_gap_policy(checked_in_policy_document)
        self.assertFalse(disabled_policy.enabled)
        with self.assertRaises(SubscriptionWorkerError):
            authorize_subscription_packet(
                self.queue,
                self.packet["packetCanonicalSha256"],
                normalized_text_resolver=self.cache,
            )
        with self.assertRaises(SubscriptionWorkerError):
            validate_ai_gap_queue(
                self.queue,
                policy=disabled_policy,
                normalized_text_resolver=self.cache,
                queue_schema=queue_schema,
            )

        tampered = copy.deepcopy(self.queue)
        tampered["budget"]["maximumCostMicrousd"] += 1
        tampered["queueCanonicalSha256"] = canonical_sha256(
            {
                key: value
                for key, value in tampered.items()
                if key != "queueCanonicalSha256"
            }
        )
        with self.assertRaises(SubscriptionWorkerError):
            validate_ai_gap_queue(
                tampered,
                policy=self.policy,
                normalized_text_resolver=self.cache,
                queue_schema=queue_schema,
            )

    def test_dry_run_never_starts_codex_or_consumes_subscription_usage(self) -> None:
        runner = Mock(side_effect=AssertionError("dry run started a subprocess"))
        result = run_subscription_packet(
            self.packet,
            self.queue_hash,
            execute=False,
            model="gpt-5.4-mini",
            runner=runner,
            environ={},
        )

        runner.assert_not_called()
        self.assertTrue(result["dryRun"])
        self.assertFalse(result["invokesModel"])
        self.assertFalse(result["apiKeyUsed"])
        self.assertFalse(result["apiBillingUsed"])

        with self.assertRaises(SubscriptionWorkerError):
            run_subscription_packet(
                self.packet,
                self.queue_hash,
                execute=True,
                confirm_subscription_usage=False,
                model="gpt-5.4-mini",
                runner=runner,
                environ={},
            )
        with self.assertRaises(SubscriptionWorkerError):
            run_subscription_packet(
                self.packet,
                self.queue_hash,
                execute=True,
                confirm_subscription_usage=True,
                model="gpt-5.4-mini",
                runner=runner,
                environ={},
            )
        with self.assertRaises(SubscriptionWorkerError):
            run_subscription_packet(
                self.authorization,
                execute=True,
                confirm_subscription_usage=True,
                model="gpt-5.4-mini",
                runner=runner,
                environ={},
            )
        runner.assert_not_called()

    def test_post_turn_failures_retain_usage_in_one_shot_ledger(self) -> None:
        output_limit = self.packet["budget"]["maxOutputTokens"]
        scenarios = (
            {
                "name": "forbidden-tool-event",
                "returncode": 0,
                "itemType": "command_execution",
                "outputTokens": 20,
                "writesCandidate": False,
                "malformedInteger": False,
                "failureCode": "post-turn-candidate-rejected",
            },
            {
                "name": "nonzero-cli-exit",
                "returncode": 9,
                "itemType": "agent_message",
                "outputTokens": 20,
                "writesCandidate": False,
                "malformedInteger": False,
                "failureCode": "post-turn-cli-failure",
            },
            {
                "name": "advisory-output-overage",
                "returncode": 0,
                "itemType": "agent_message",
                "outputTokens": output_limit + 1,
                "writesCandidate": True,
                "malformedInteger": False,
                "failureCode": "post-turn-candidate-rejected",
            },
            {
                "name": "oversized-json-integer",
                "returncode": 0,
                "itemType": "agent_message",
                "outputTokens": 20,
                "writesCandidate": True,
                "malformedInteger": True,
                "failureCode": "post-turn-candidate-rejected",
            },
        )
        trusted_lock = load_trusted_codex_lock()
        for scenario in scenarios:
            with self.subTest(scenario=scenario["name"]):
                policy_path, queue_schema_path = self._enabled_policy_contract(
                    scenario["name"]
                )
                review_root = self.root / f"review-{scenario['name']}"
                review_root.mkdir()
                output_tokens = scenario["outputTokens"]
                usage = {
                    "input_tokens": 100,
                    "cached_input_tokens": 0,
                    "output_tokens": output_tokens,
                    "total_tokens": 100 + output_tokens,
                }
                events = (
                    {"type": "thread.started", "thread_id": "test"},
                    {
                        "type": "item.completed",
                        "item": {
                            "type": scenario["itemType"],
                            "text": "{}",
                        },
                    },
                    {"type": "turn.completed", "usage": usage},
                )
                verifier = Mock(
                    return_value=(self.root / "codex.exe", trusted_lock)
                )

                def runner(command: list[str], **kwargs: object) -> object:
                    del kwargs
                    if len(command) > 1 and command[1] == "--version":
                        return SimpleNamespace(
                            returncode=0,
                            stdout=trusted_lock["codexCliVersion"] + "\n",
                            stderr="",
                        )
                    if len(command) > 2 and command[1:3] == [
                        "login",
                        "status",
                    ]:
                        return SimpleNamespace(
                            returncode=0,
                            stdout="",
                            stderr="Logged in using ChatGPT\n",
                        )
                    if scenario["writesCandidate"]:
                        message_index = command.index(
                            "--output-last-message"
                        )
                        response_text = (
                            '{"oversizedInteger":'
                            + ("9" * 5_000)
                            + "}"
                            if scenario["malformedInteger"]
                            else json.dumps(self._candidate_output())
                        )
                        Path(command[message_index + 1]).write_text(
                            response_text,
                            encoding="utf-8",
                        )
                    return SimpleNamespace(
                        returncode=scenario["returncode"],
                        stdout="\n".join(
                            json.dumps(event) for event in events
                        ),
                        stderr="simulated",
                    )

                with (
                    patch(
                        "national.subscription_worker.AI_GAP_POLICY_PATH",
                        policy_path,
                    ),
                    patch(
                        "national.subscription_worker.AI_GAP_QUEUE_SCHEMA_PATH",
                        queue_schema_path,
                    ),
                    patch(
                        "national.subscription_worker._fixed_subscription_review_root",
                        return_value=review_root,
                    ),
                    patch(
                        "national.subscription_worker.assert_local_operator_environment"
                    ),
                    patch(
                        "national.subscription_worker._sanitized_child_environment",
                        return_value={"PATH": "trusted-child-path"},
                    ),
                    patch(
                        "national.subscription_worker.verify_trusted_codex_installation",
                        verifier,
                    ),
                    patch(
                        "national.subscription_worker._CONSUMED_ATTEMPTS",
                        set(),
                    ),
                ):
                    authorization = authorize_subscription_packet(
                        self.queue,
                        self.packet["packetCanonicalSha256"],
                        normalized_text_resolver=self.cache,
                    )
                    attempt = claim_subscription_attempt(
                        authorization,
                        model="gpt-5.4-mini",
                        environ={},
                    )
                    with self.assertRaises(
                        SubscriptionRunFailure
                    ) as failure:
                        run_subscription_packet(
                            attempt,
                            execute=True,
                            confirm_subscription_usage=True,
                            model="gpt-5.4-mini",
                            runner=runner,
                            environ={"PATH": "original-codex-locator"},
                        )
                    self.assertEqual(
                        verifier.call_args.kwargs["environ"],
                        {"PATH": "original-codex-locator"},
                    )
                    self.assertEqual(
                        failure.exception.failure_code,
                        scenario["failureCode"],
                    )
                    self.assertEqual(
                        failure.exception.observed_usage["outputTokens"],
                        output_tokens,
                    )
                    finish_subscription_attempt(
                        attempt,
                        status="failed",
                        failure_code=failure.exception.failure_code,
                        observed_usage=failure.exception.observed_usage,
                    )
                    ledger = parse_strict_json(
                        attempt.ledger_path.read_bytes()
                    )
                    self.assertEqual(ledger["status"], "failed")
                    self.assertEqual(
                        ledger["failureCode"],
                        scenario["failureCode"],
                    )
                    self.assertEqual(
                        ledger["subscriptionUsage"]["outputTokens"],
                        output_tokens,
                    )
                    self.assertEqual(
                        ledger["subscriptionUsage"][
                            "outputWithinPacketAdvisoryLimit"
                        ],
                        output_tokens <= output_limit,
                    )
                    with self.assertRaises(SubscriptionWorkerError):
                        finish_subscription_attempt(
                            attempt,
                            status="failed",
                            failure_code=failure.exception.failure_code,
                            observed_usage=failure.exception.observed_usage,
                        )

    def test_cli_forwards_observed_usage_for_post_turn_failures(self) -> None:
        usage = {
            "inputTokens": 100,
            "cachedInputTokens": 0,
            "outputTokens": 20,
            "totalTokens": 120,
        }
        cases = (
            {
                "name": "worker-rejection",
                "liveResult": SubscriptionRunFailure(
                    "simulated post-turn rejection",
                    failure_code="post-turn-candidate-rejected",
                    observed_usage=usage,
                ),
                "persistFailure": None,
                "expectedCode": "post-turn-candidate-rejected",
            },
            {
                "name": "local-persistence-rejection",
                "liveResult": {
                    "subscriptionUsage": {
                        **usage,
                        "observedAfterRun": True,
                        "preventiveOutputTokenCapAvailable": False,
                        "outputWithinPacketAdvisoryLimit": True,
                    }
                },
                "persistFailure": SubscriptionWorkerError(
                    "simulated local persistence rejection"
                ),
                "expectedCode": "post-turn-local-persistence-failed",
            },
        )
        for case in cases:
            with self.subTest(case=case["name"]):
                attempt = SimpleNamespace(
                    attempt_canonical_sha256="d" * 64
                )
                worker = Mock(
                    side_effect=[
                        {"dryRun": True},
                        case["liveResult"],
                    ]
                )
                persistence = Mock()
                if case["persistFailure"] is not None:
                    persistence.side_effect = case["persistFailure"]
                finisher = Mock()
                with (
                    patch.object(
                        review_cli,
                        "_object",
                        return_value=self.queue,
                    ),
                    patch.object(
                        review_cli,
                        "ContentAddressedSourceCache",
                        return_value=self.cache,
                    ),
                    patch.object(
                        review_cli,
                        "authorize_subscription_packet",
                        return_value=self.authorization,
                    ),
                    patch.object(
                        review_cli,
                        "run_subscription_packet",
                        worker,
                    ),
                    patch.object(
                        review_cli,
                        "assert_local_operator_environment",
                    ),
                    patch.object(
                        review_cli,
                        "claim_subscription_attempt",
                        return_value=attempt,
                    ),
                    patch.object(
                        review_cli,
                        "persist_subscription_candidate",
                        persistence,
                    ),
                    patch.object(
                        review_cli,
                        "finish_subscription_attempt",
                        finisher,
                    ),
                    patch("builtins.print"),
                ):
                    exit_code = review_cli.main(
                        [
                            "--queue",
                            str(self.root / "queue.json"),
                            "--packet-sha256",
                            self.packet["packetCanonicalSha256"],
                            "--source-cache",
                            str(self.root / "cache"),
                            "--execute",
                            "--confirm-subscription-usage",
                        ]
                    )
                self.assertEqual(exit_code, 2)
                finisher.assert_called_once_with(
                    attempt,
                    status="failed",
                    failure_code=case["expectedCode"],
                    observed_usage=usage,
                )

    def test_attempt_ledger_is_acquired_before_duplicate_subscription_use(
        self,
    ) -> None:
        policy_document = parse_strict_json(
            (
                Path(__file__).resolve().parents[1]
                / "national"
                / "ai_gap_policy.json"
            ).read_bytes()
        )
        policy_document["enabled"] = True
        policy_path = self.root / "enabled-policy.json"
        queue_schema_path = self.root / "queue-schema.json"
        policy_path.write_text(
            json.dumps(policy_document),
            encoding="utf-8",
        )
        queue_schema_path.write_text(
            json.dumps(self.queue_schema),
            encoding="utf-8",
        )
        review_root = self.root / "review"
        review_root.mkdir()
        with (
            patch(
                "national.subscription_worker.AI_GAP_POLICY_PATH",
                policy_path,
            ),
            patch(
                "national.subscription_worker.AI_GAP_QUEUE_SCHEMA_PATH",
                queue_schema_path,
            ),
            patch(
                "national.subscription_worker._fixed_subscription_review_root",
                return_value=review_root,
            ),
            patch(
                "national.subscription_worker.assert_local_operator_environment"
            ),
        ):
            live_authorization = authorize_subscription_packet(
                self.queue,
                self.packet["packetCanonicalSha256"],
                normalized_text_resolver=self.cache,
            )
            claim_subscription_attempt(
                live_authorization,
                model="gpt-5.4-mini",
                environ={},
            )
            with self.assertRaises(SubscriptionWorkerError):
                claim_subscription_attempt(
                    live_authorization,
                    model="gpt-5.4-mini",
                    environ={},
                )

    def test_candidate_envelope_can_only_enter_human_review(self) -> None:
        model_output = self._candidate_output()
        verified = verify_model_output(
            self.packet,
            model_output,
            prompt_canonical_sha256=self.prompt_hash,
        )
        envelope = build_candidate_envelope(
            self.packet,
            verified,
            queue_canonical_sha256=self.queue_hash,
            prompt_canonical_sha256=self.prompt_hash,
            output_schema=self.output_schema,
            model_identifier="gpt-5.4-mini",
            codex_cli_version="codex-cli 0.144.4",
            codex_cli_binary_sha256=load_trusted_codex_lock()[
                "executableSha256"
            ],
            subscription_usage={
                "inputTokens": 100,
                "cachedInputTokens": 0,
                "outputTokens": 20,
                "totalTokens": 120,
            },
        )

        self.assertEqual(envelope["authMode"], "chatgpt-subscription")
        self.assertFalse(envelope["apiKeyUsed"])
        self.assertFalse(envelope["apiBillingUsed"])
        self.assertEqual(envelope["queueCanonicalSha256"], self.queue_hash)
        self.assertEqual(
            envelope["packetCanonicalSha256"],
            self.packet["packetCanonicalSha256"],
        )
        self.assertEqual(envelope["promptCanonicalSha256"], self.prompt_hash)
        self.assertEqual(
            envelope["outputSchemaCanonicalSha256"],
            canonical_sha256(self.output_schema),
        )
        self.assertEqual(
            envelope["modelResponseCanonicalSha256"],
            canonical_sha256(model_output),
        )
        self.assertEqual(envelope["verificationStatus"], "verified")
        self.assertTrue(envelope["humanReviewRequired"])
        self.assertFalse(envelope["mayAutoPublish"])
        self.assertEqual(envelope["publicationStatus"], "pending-human-review")
        self.assertEqual(envelope["fieldDecisions"], model_output["fieldDecisions"])
        claimed_hash = envelope["resultCanonicalSha256"]
        self.assertEqual(
            claimed_hash,
            canonical_sha256(
                {
                    key: value
                    for key, value in envelope.items()
                    if key != "resultCanonicalSha256"
                }
            ),
        )
        candidate_schema = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "national"
                / "schemas"
                / "subscription-gap-candidate.schema.json"
            ).read_text(encoding="utf-8")
        )
        Draft202012Validator(candidate_schema).validate(envelope)
        validate_candidate_schema(
            envelope,
            authorization=self.authorization,
        )

        publishable = {
            **envelope,
            "mayAutoPublish": True,
        }
        publishable["resultCanonicalSha256"] = canonical_sha256(
            {
                key: value
                for key, value in publishable.items()
                if key != "resultCanonicalSha256"
            }
        )
        with self.assertRaises(SubscriptionWorkerError):
            validate_candidate_schema(
                publishable,
                authorization=self.authorization,
            )

        replayed = {
            **envelope,
            "promptCanonicalSha256": "e" * 64,
        }
        replayed["resultCanonicalSha256"] = canonical_sha256(
            {
                key: value
                for key, value in replayed.items()
                if key != "resultCanonicalSha256"
            }
        )
        with self.assertRaises(SubscriptionWorkerError):
            validate_candidate_schema(
                replayed,
                authorization=self.authorization,
            )


if __name__ == "__main__":
    unittest.main()
