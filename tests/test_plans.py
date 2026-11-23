from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "progressive-plan" / "scripts" / "progressive_plan.py"
RESUME = ROOT / "skills" / "plan-resume" / "scripts" / "resume_status.py"
sys.path.insert(0, str(ROOT / "skills" / "progressive-plan" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import planlib  # noqa: E402
from fixtures import init_git, make_valid_plan, valid_master, valid_plan  # noqa: E402


def run_cli(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class PlanTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pplan-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def new_plan(self) -> Path:
        result = run_cli(self.tmp, "new", "Test Plan", "--root", "plans", "--size", "small")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return self.tmp / "plans" / "test-plan"

    def master(self, plan_dir: Path) -> str:
        return (plan_dir / "master.md").read_text(encoding="utf-8")

    def plan(self, plan_dir: Path) -> str:
        return (plan_dir / "phases" / "01-build" / "plan.md").read_text(encoding="utf-8")

    def assert_ok(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class ParserTests(unittest.TestCase):
    def test_phase_rows_well_formed_and_malformed(self) -> None:
        master = """## Phase map

| ID | Phase | Outcome | Depends on | Status | Plan |
|---|---|---|---|---|---|
| P1 | Build | Add behavior | none | ready | [plan](p1) |
| P9 | Broken |"""
        self.assertEqual(
            planlib.phase_rows(master),
            [
                {
                    "id": "P1",
                    "name": "Build",
                    "outcome": "Add behavior",
                    "depends": "none",
                    "status": "ready",
                    "plan": "[plan](p1)",
                    "malformed": False,
                    "raw": "| P1 | Build | Add behavior | none | ready | [plan](p1) |",
                },
                {
                    "id": "P9",
                    "name": "Broken",
                    "outcome": "",
                    "depends": "",
                    "status": "",
                    "plan": "",
                    "malformed": True,
                    "raw": "| P9 | Broken |",
                },
            ],
        )

    def test_ledger_rows_well_formed_and_malformed(self) -> None:
        master = """## Discovery ledger

| ID | Date | Phase | Affects | Discovery | Type | Action taken | Status |
|---|---|---|---|---|---|---|---|
| L1 | 2026-11-14 | P1 | P1 | Found a constraint | note | Recorded | open |
| L9 | 2026-11-14 | P1 | P1 | Broken | note |"""
        self.assertEqual(
            planlib.ledger_rows(master),
            [
                {
                    "id": "L1",
                    "date": "2026-11-14",
                    "phase": "P1",
                    "affects": "P1",
                    "discovery": "Found a constraint",
                    "type": "note",
                    "action": "Recorded",
                    "status": "open",
                    "malformed": False,
                    "raw": "| L1 | 2026-11-14 | P1 | P1 | Found a constraint | note | Recorded | open |",
                },
                {
                    "id": "L9",
                    "date": "2026-11-14",
                    "phase": "P1",
                    "affects": "P1",
                    "discovery": "Broken",
                    "type": "note",
                    "action": "",
                    "status": "",
                    "malformed": True,
                    "raw": "| L9 | 2026-11-14 | P1 | P1 | Broken | note |",
                },
            ],
        )

    def test_decision_rows_well_formed_and_malformed(self) -> None:
        master = """## Cross-phase decisions

| ID | Date | Decision | Reason | Affects |
|---|---|---|---|---|
| C1 | 2026-11-14 | Use the parser | Less duplication | all |
| C9 | 2026-11-14 | Broken |"""
        self.assertEqual(
            planlib.decision_rows(master),
            [
                {
                    "id": "C1",
                    "date": "2026-11-14",
                    "decision": "Use the parser",
                    "reason": "Less duplication",
                    "affects": "all",
                    "malformed": False,
                    "raw": "| C1 | 2026-11-14 | Use the parser | Less duplication | all |",
                },
                {
                    "id": "C9",
                    "date": "2026-11-14",
                    "decision": "Broken",
                    "reason": "",
                    "affects": "",
                    "malformed": True,
                    "raw": "| C9 | 2026-11-14 | Broken |",
                },
            ],
        )

    def test_closeout_history_rows_well_formed_and_malformed(self) -> None:
        master = """## Closeout history

| Phase | Date | Verdict | Criteria met | Commit | Report |
|---|---|---|---|---|---|
| P1 | 2026-11-14 | addressed | A1 | abc1234 | [report](p1) |
| P9 | 2026-11-15 | partial | A1 |"""
        self.assertEqual(
            planlib.closeout_history_rows(master),
            [
                {
                    "phase": "P1",
                    "date": "2026-11-14",
                    "verdict": "addressed",
                    "criteria": "A1",
                    "commit": "abc1234",
                    "report": "[report](p1)",
                    "malformed": False,
                },
                {
                    "phase": "P9",
                    "date": "2026-11-15",
                    "verdict": "partial",
                    "criteria": "A1",
                    "commit": "",
                    "report": "",
                    "malformed": True,
                },
            ],
        )

    def test_definition_items_checked_unchecked_verify(self) -> None:
        master = """## Definition of done

- [x] D1 — The command prints ok — verify: `python3 -c "print('ok')"`
- [ ] D2 — The command is tested
- [X] D3 — The command is documented — verify: `readme exists`"""
        self.assertEqual(
            planlib.definition_items(master),
            [
                {
                    "id": "D1",
                    "checked": True,
                    "text": 'The command prints ok — verify: `python3 -c "print(\'ok\')"`',
                    "verify": '`python3 -c "print(\'ok\')"`',
                },
                {
                    "id": "D2",
                    "checked": False,
                    "text": "The command is tested",
                    "verify": "",
                },
                {
                    "id": "D3",
                    "checked": True,
                    "text": "The command is documented — verify: `readme exists`",
                    "verify": "`readme exists`",
                },
            ],
        )

    def test_acceptance_items_checked_unchecked_verify(self) -> None:
        plan = """## Phase acceptance criteria

- [x] A1 — The command prints ok — verify: `python3 -c "print('ok')"`
- [ ] A2 — The command is tested
- [X] A3 — The command is documented — verify: `readme exists`"""
        self.assertEqual(
            planlib.acceptance_items(plan),
            [
                {
                    "id": "A1",
                    "checked": True,
                    "text": 'The command prints ok — verify: `python3 -c "print(\'ok\')"`',
                    "verify": '`python3 -c "print(\'ok\')"`',
                },
                {
                    "id": "A2",
                    "checked": False,
                    "text": "The command is tested",
                    "verify": "",
                },
                {
                    "id": "A3",
                    "checked": True,
                    "text": "The command is documented — verify: `readme exists`",
                    "verify": "`readme exists`",
                },
            ],
        )

    def test_closeout_verdict_with_and_without_verdict(self) -> None:
        plan = """## Closeout

- Verdict: Addressed
- Steps complete: S1
"""
        self.assertEqual(planlib.closeout_verdict(plan), "addressed")
        self.assertIsNone(
            planlib.closeout_verdict("""## Closeout

- Steps complete: S1
""")
        )

    def test_identifier_number(self) -> None:
        self.assertEqual(planlib.identifier_number("P12"), 12)
        self.assertEqual(planlib.identifier_number("L7"), 7)
        self.assertEqual(planlib.identifier_number("master"), 0)


class ScaffoldTests(PlanTestCase):
    def test_new_records_root_and_size(self) -> None:
        plan_dir = self.new_plan()
        master = self.master(plan_dir)
        self.assertIn("Size: small", master)
        self.assertIn("Mode: standard", master)
        self.assertIn("Plan directory: `plans/test-plan`", master)
        self.assertIn("Branch: `plan/test-plan`", master)

    def test_new_rejects_slug_escape(self) -> None:
        result = run_cli(
            self.tmp, "new", "Escape", "--root", "plans", "--slug", "../escaped"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.tmp / "plans" / ".." / "escaped").resolve().exists())

    def test_draft_and_outline_pass(self) -> None:
        plan_dir = self.new_plan()
        self.assert_ok(run_cli(self.tmp, "check", str(plan_dir)))
        result = run_cli(
            self.tmp,
            "add-phase",
            str(plan_dir),
            "First phase",
            "--depends",
            "none",
            "--outcome",
            "Build the thing",
            "--outline",
        )
        self.assert_ok(result)
        self.assert_ok(run_cli(self.tmp, "check", str(plan_dir)))
        self.assertIn("Master version: 2", self.master(plan_dir))

    def test_write_plan_for_outline(self) -> None:
        plan_dir = self.new_plan()
        self.assert_ok(
            run_cli(self.tmp, "add-phase", str(plan_dir), "First phase", "--outline")
        )
        result = run_cli(self.tmp, "write-plan", str(plan_dir), "P1")
        self.assert_ok(result)
        self.assertTrue((plan_dir / "phases" / "01-first-phase" / "plan.md").exists())
        self.assert_ok(run_cli(self.tmp, "check", str(plan_dir)))

    def test_small_plan_uses_compact_templates(self) -> None:
        plan_dir = self.new_plan()
        self.assertIn('A["User request"]', self.master(plan_dir))
        self.assert_ok(
            run_cli(self.tmp, "add-phase", str(plan_dir), "First phase")
        )
        plan_text = (plan_dir / "phases" / "01-first-phase" / "plan.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Keep this phase to one outcome.", plan_text)

    def test_add_phase_preserves_insertion_order(self) -> None:
        plan_dir = self.new_plan()
        for name in ("First phase", "Second phase", "Third phase"):
            self.assert_ok(
                run_cli(self.tmp, "add-phase", str(plan_dir), name, "--outline")
            )
        ids = [row["id"] for row in planlib.phase_rows(self.master(plan_dir))]
        self.assertEqual(ids, ["P1", "P2", "P3"])


class YoloModeTests(PlanTestCase):
    def test_new_yolo_records_mode_and_authorization(self) -> None:
        result = run_cli(
            self.tmp,
            "new",
            "Overnight Plan",
            "--root",
            "plans",
            "--mode",
            "yolo",
            "--authorized-by",
            "Jorge",
        )
        self.assert_ok(result)
        master = self.master(self.tmp / "plans" / "overnight-plan")
        self.assertIn("- Mode: yolo", master)
        self.assertIn(
            f"- Mode authorized by: Jorge, {date.today().isoformat()}", master
        )
        self.assert_ok(run_cli(self.tmp, "check", "plans/overnight-plan"))

    def test_new_yolo_requires_authorized_by(self) -> None:
        result = run_cli(
            self.tmp, "new", "Unsafe", "--root", "plans", "--mode", "yolo"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires --authorized-by", result.stdout + result.stderr)
        self.assertFalse((self.tmp / "plans" / "unsafe").exists())

    def test_check_rejects_yolo_without_authorization(self) -> None:
        plan_dir = self.new_plan()
        master = self.master(plan_dir).replace("- Mode: standard", "- Mode: yolo", 1)
        (plan_dir / "master.md").write_text(master, encoding="utf-8")
        result = run_cli(self.tmp, "check", str(plan_dir))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Mode authorized by", result.stdout + result.stderr)

    def test_check_rejects_unknown_mode(self) -> None:
        plan_dir = self.new_plan()
        master = self.master(plan_dir).replace("- Mode: standard", "- Mode: turbo", 1)
        (plan_dir / "master.md").write_text(master, encoding="utf-8")
        result = run_cli(self.tmp, "check", str(plan_dir))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Mode must be one of", result.stdout + result.stderr)

    def test_status_reports_mode(self) -> None:
        self.assert_ok(
            run_cli(
                self.tmp,
                "new",
                "Overnight Plan",
                "--root",
                "plans",
                "--mode",
                "yolo",
                "--authorized-by",
                "Jorge",
            )
        )
        result = run_cli(self.tmp, "status", "plans/overnight-plan", "--json")
        self.assert_ok(result)
        self.assertEqual(json.loads(result.stdout)["mode"], "yolo")

    def test_approve_yolo_requires_yolo_master(self) -> None:
        make_valid_plan(self.tmp, "planned")
        result = run_cli(
            self.tmp, "approve", "plans/valid-plan", "P1", "--by", "Jorge", "--yolo"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires a master plan with '- Mode: yolo'", result.stdout + result.stderr)

    def test_approve_yolo_records_authorization(self) -> None:
        plan_dir = make_valid_plan(self.tmp, "planned")
        master = self.master(plan_dir).replace(
            "- Size: small\n",
            "- Size: small\n- Mode: yolo\n- Mode authorized by: Jorge, 2026-11-20\n",
            1,
        )
        (plan_dir / "master.md").write_text(master, encoding="utf-8")
        result = run_cli(
            self.tmp, "approve", str(plan_dir), "P1", "--by", "Jorge", "--yolo"
        )
        self.assert_ok(result)
        self.assertIn("- Approved by: Jorge (yolo)", self.plan(plan_dir))
        self.assert_ok(run_cli(self.tmp, "check", str(plan_dir)))


class ApprovalTests(PlanTestCase):
    def test_approve_refuses_empty_template(self) -> None:
        plan_dir = self.new_plan()
        self.assert_ok(
            run_cli(self.tmp, "add-phase", str(plan_dir), "First phase")
        )
        result = run_cli(self.tmp, "approve", str(plan_dir), "P1", "--by", "Jorge")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("placeholder", result.stdout + result.stderr)
        plan_text = (plan_dir / "phases" / "01-first-phase" / "plan.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Status: draft", plan_text)

    def test_approve_valid_plan(self) -> None:
        make_valid_plan(self.tmp, "planned")
        result = run_cli(
            self.tmp, "approve", "plans/valid-plan", "P1", "--by", "Jorge"
        )
        self.assert_ok(result)
        self.assert_ok(run_cli(self.tmp, "check", "plans/valid-plan"))
        self.assertIn("Status: ready", self.plan(self.tmp / "plans" / "valid-plan"))

    def test_approve_rejects_stale_master_version(self) -> None:
        plan_dir = make_valid_plan(self.tmp, "planned")
        master = self.master(plan_dir).replace("- Master version: 1", "- Master version: 2", 1)
        (plan_dir / "master.md").write_text(master, encoding="utf-8")
        result = run_cli(self.tmp, "approve", str(plan_dir), "P1", "--by", "Jorge")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("validated against master v1", result.stdout + result.stderr)

    def test_add_phase_bumps_master_version(self) -> None:
        plan_dir = self.new_plan()
        self.assert_ok(
            run_cli(self.tmp, "add-phase", str(plan_dir), "First phase", "--outline")
        )
        self.assertIn("Master version: 2", self.master(plan_dir))

    def test_missing_master_version_fails(self) -> None:
        plan_dir = self.new_plan()
        master = self.master(plan_dir).replace("- Master version: 1\n", "", 1)
        (plan_dir / "master.md").write_text(master, encoding="utf-8")
        result = run_cli(
            self.tmp, "add-phase", str(plan_dir), "First phase", "--outline"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "master plan has no '- Master version: N' line",
            result.stdout + result.stderr,
        )

    def test_add_phase_rejects_unknown_dependency(self) -> None:
        plan_dir = self.new_plan()
        result = run_cli(
            self.tmp,
            "add-phase",
            str(plan_dir),
            "First phase",
            "--depends",
            "P9",
            "--outline",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown phase P9", result.stdout + result.stderr)

    def test_check_strict_turns_warning_into_error(self) -> None:
        plan_dir = self.new_plan()
        self.assert_ok(run_cli(self.tmp, "check", str(plan_dir)))
        result = run_cli(self.tmp, "check", str(plan_dir), "--strict")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("warning treated as error", result.stdout + result.stderr)


class StructureTests(PlanTestCase):
    def test_malformed_phase_row_is_error(self) -> None:
        plan_dir = self.new_plan()
        master = self.master(plan_dir)
        lines = master.splitlines()
        index = next(i for i, line in enumerate(lines) if line.startswith("| ID | Phase |"))
        lines.insert(index + 2, "| P1 | Broken | no plan |")
        (plan_dir / "master.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = run_cli(self.tmp, "check", str(plan_dir))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("malformed phase row", result.stdout + result.stderr)

    def test_dependency_cycle_is_error(self) -> None:
        plan_dir = self.new_plan()
        self.assert_ok(
            run_cli(
                self.tmp,
                "add-phase",
                str(plan_dir),
                "One",
                "--depends",
                "none",
                "--outline",
            )
        )
        self.assert_ok(
            run_cli(
                self.tmp,
                "add-phase",
                str(plan_dir),
                "Two",
                "--depends",
                "P1",
                "--outline",
            )
        )
        master = self.master(plan_dir)
        master = master.replace(
            "| P1 | One | TBD | none | planned | pending |",
            "| P1 | One | TBD | P2 | planned | pending |",
            1,
        )
        (plan_dir / "master.md").write_text(master, encoding="utf-8")
        result = run_cli(self.tmp, "check", str(plan_dir))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dependency cycle", result.stdout + result.stderr)

    def test_unknown_prior_discovery_is_error(self) -> None:
        plan_dir = make_valid_plan(self.tmp, "ready")
        plan_file = plan_dir / "phases" / "01-build" / "plan.md"
        plan_text = plan_file.read_text(encoding="utf-8").replace(
            "| None | none | No ledger rows affect this phase. |",
            "| L9 | missing | Applied. |",
            1,
        )
        plan_file.write_text(plan_text, encoding="utf-8")
        result = run_cli(self.tmp, "check", str(plan_dir))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown ledger row L9", result.stdout + result.stderr)

    def test_invalid_history_is_error(self) -> None:
        plan_dir = make_valid_plan(self.tmp, "ready")
        master = self.master(plan_dir).replace(
            "- Branch: `plan/valid-plan`",
            "- Branch: `plan/valid-plan`\n- History: everything",
            1,
        )
        (plan_dir / "master.md").write_text(master, encoding="utf-8")
        result = run_cli(self.tmp, "check", str(plan_dir))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("History must be", result.stdout + result.stderr)

    def test_invalid_ledger_row_is_error(self) -> None:
        plan_dir = self.new_plan()
        master = self.master(plan_dir)
        lines = master.splitlines()
        index = next(i for i, line in enumerate(lines) if line.startswith("| ID | Date | Phase | Affects |"))
        lines.insert(
            index + 2,
            "| L1 | 2026-11-14 | P1 | P99 | Found | bogus |  | open |",
        )
        (plan_dir / "master.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = run_cli(self.tmp, "check", str(plan_dir))
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown phase P99", output)
        self.assertIn("invalid type", output)


class DiscoveryTests(PlanTestCase):
    def test_add_discovery_appends_and_bumps(self) -> None:
        plan_dir = make_valid_plan(self.tmp, "ready")
        result = run_cli(
            self.tmp,
            "add-discovery",
            str(plan_dir),
            "P1",
            "Found a constraint",
            "--affects",
            "P1",
            "--type",
            "note",
            "--action",
            "Recorded",
        )
        self.assert_ok(result)
        master = self.master(plan_dir)
        self.assertIn("| L1 |", master)
        self.assertIn("Master version: 2", master)
        check = run_cli(self.tmp, "check", str(plan_dir))
        self.assertNotEqual(check.returncode, 0)
        self.assertIn("missing ledger L1", check.stdout + check.stderr)

    def test_add_decision_appends(self) -> None:
        plan_dir = self.new_plan()
        result = run_cli(
            self.tmp,
            "add-decision",
            str(plan_dir),
            "Use the existing parser",
            "--reason",
            "Less duplication",
            "--affects",
            "all",
        )
        self.assert_ok(result)
        master = self.master(plan_dir)
        self.assertIn("| C1 |", master)
        self.assertIn("Master version: 2", master)

    def test_add_discovery_no_bump_skips_version_and_warning(self) -> None:
        plan_dir = make_valid_plan(self.tmp, "ready")
        result = run_cli(
            self.tmp,
            "add-discovery",
            str(plan_dir),
            "P1",
            "Found a constraint",
            "--affects",
            "P1",
            "--type",
            "note",
            "--action",
            "Recorded",
            "--no-bump",
        )
        self.assert_ok(result)
        self.assertIn("Master version: 1", self.master(plan_dir))
        self.assertNotIn(
            "warning: master version bumped", result.stdout + result.stderr
        )


class CommitAndCloseTests(PlanTestCase):
    def test_record_commit_rejects_wrong_head_subject(self) -> None:
        init_git(self.tmp)
        make_valid_plan(self.tmp, "in_progress")
        result = run_cli(
            self.tmp, "record-commit", "plans/valid-plan", "P1", "--by", "worker-1"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not look like the P1 commit", result.stdout + result.stderr)

    def test_record_commit_rejects_non_ancestor_commit(self) -> None:
        init_git(self.tmp)
        subprocess.run(["git", "checkout", "-b", "side"], cwd=self.tmp, check=True)
        (self.tmp / "side.txt").write_text("side", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.tmp, check=True)
        subprocess.run(["git", "commit", "-qm", "side"], cwd=self.tmp, check=True)
        side_hash = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=self.tmp,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
        subprocess.run(["git", "checkout", "-"], cwd=self.tmp, check=True)
        plan_dir = make_valid_plan(self.tmp, "in_progress")
        result = run_cli(
            self.tmp, "record-commit", str(plan_dir), "P1", "--hash", side_hash
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is not an ancestor of HEAD", result.stdout + result.stderr)

    def test_record_commit_accepts_phase_commit(self) -> None:
        init_git(self.tmp)
        plan_dir = make_valid_plan(self.tmp, "in_progress")
        (self.tmp / "app.py").write_text("ok\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.tmp, check=True)
        subprocess.run(["git", "commit", "-qm", "P1: Build"], cwd=self.tmp, check=True)
        result = run_cli(
            self.tmp, "record-commit", str(plan_dir), "P1", "--by", "worker-1"
        )
        self.assert_ok(result)
        plan = self.plan(plan_dir)
        self.assertIn("- Commit: ", plan)
        self.assertIn("- Implemented by: worker-1", plan)
        self.assert_ok(run_cli(self.tmp, "check", str(plan_dir)))

    def _close_ready(self, *, break_standards: bool = False) -> tuple[Path, str]:
        init_git(self.tmp)
        plan_dir = make_valid_plan(self.tmp, "in_progress", dod_checked=True)
        (self.tmp / "app.py").write_text("ok\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.tmp, check=True)
        subprocess.run(["git", "commit", "-qm", "P1: Build"], cwd=self.tmp, check=True)
        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=self.tmp,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
        ready = valid_plan("done", commit_hash=head).replace(
            "- Status: done", "- Status: in_progress", 1
        )
        if break_standards:
            ready = ready.replace("- [x] The diff is", "- [ ] The diff is", 1)
        (plan_dir / "phases" / "01-build" / "plan.md").write_text(
            ready, encoding="utf-8"
        )
        return plan_dir, head

    def test_close_sets_done_and_history(self) -> None:
        plan_dir, head = self._close_ready()
        result = run_cli(
            self.tmp, "close", str(plan_dir), "P1", "--by", "worker-1"
        )
        self.assert_ok(result)
        master = self.master(plan_dir)
        self.assertIn("| P1 | Build | Add the behavior | none | done |", master)
        self.assertIn("Status: complete", master)
        self.assertIn("| P1 |", master.split("## 11. Closeout history")[1])
        self.assert_ok(run_cli(self.tmp, "check", str(plan_dir)))

    def test_close_rejects_unchecked_standards(self) -> None:
        plan_dir, _head = self._close_ready(break_standards=True)
        result = run_cli(
            self.tmp, "close", str(plan_dir), "P1", "--by", "worker-1"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("code standards check item", result.stdout + result.stderr)
        self.assertIn("| P1 | Build | Add the behavior | none | in_progress |", self.master(plan_dir))


class ArchiveTests(PlanTestCase):
    def test_archive_moves_completed_plan(self) -> None:
        init_git(self.tmp)
        plan_dir = make_valid_plan(self.tmp, "done")
        result = run_cli(self.tmp, "archive", str(plan_dir))
        self.assert_ok(result)
        target = self.tmp / "plans" / "archive" / "valid-plan"
        self.assertFalse(plan_dir.exists())
        self.assertTrue((target / "master.md").exists())
        self.assertIn(
            "Plan directory: `plans/archive/valid-plan`",
            (target / "master.md").read_text(encoding="utf-8"),
        )

    def test_archive_uses_custom_destination(self) -> None:
        init_git(self.tmp)
        plan_dir = make_valid_plan(self.tmp, "done")
        result = run_cli(
            self.tmp, "archive", str(plan_dir), "--dest", "plans/done"
        )
        self.assert_ok(result)
        self.assertTrue(
            (self.tmp / "plans" / "done" / "valid-plan" / "master.md").exists()
        )

    def test_archive_rejects_incomplete_plan(self) -> None:
        plan_dir = make_valid_plan(self.tmp, "ready")
        result = run_cli(self.tmp, "archive", str(plan_dir))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not complete", result.stdout + result.stderr)
        self.assertTrue(plan_dir.exists())

    def test_archive_rejects_existing_destination(self) -> None:
        plan_dir = make_valid_plan(self.tmp, "done")
        target = self.tmp / "plans" / "archive" / "valid-plan"
        target.mkdir(parents=True)
        result = run_cli(self.tmp, "archive", str(plan_dir))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already exists", result.stdout + result.stderr)
        self.assertTrue(plan_dir.exists())


class CondenseTests(PlanTestCase):
    def _commit(self, message: str) -> str:
        subprocess.run(["git", "add", "-A"], cwd=self.tmp, check=True)
        subprocess.run(["git", "commit", "-qm", message], cwd=self.tmp, check=True)
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=self.tmp,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()

    def _done_phase(self) -> tuple[Path, str]:
        plan_dir = make_valid_plan(self.tmp, "in_progress")
        self._commit("plan: P1 Build")
        (self.tmp / "app.py").write_text("ok\n", encoding="utf-8")
        phase = self._commit("P1: Build")
        master = valid_master(plan_dir, "done", dod_checked=True).replace(
            "- Status: active", "- Status: complete", 1
        )
        (plan_dir / "master.md").write_text(master, encoding="utf-8")
        (plan_dir / "phases" / "01-build" / "plan.md").write_text(
            valid_plan("done", commit_hash=phase), encoding="utf-8"
        )
        self._commit("P1: record closeout")
        return plan_dir, phase

    def _log(self, branch: str, base: str) -> list[str]:
        return subprocess.run(
            ["git", "log", "--reverse", "--format=%s", branch, "--not", base],
            cwd=self.tmp,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.splitlines()

    def test_condense_drops_plans_and_rebuilds_one_commit(self) -> None:
        base = init_git(self.tmp)
        plan_dir, _phase = self._done_phase()
        result = run_cli(
            self.tmp,
            "condense",
            str(plan_dir),
            "--base",
            base,
            "--branch",
            "condensed",
            "--plans",
            "drop",
            "--json",
        )
        self.assert_ok(result)
        data = json.loads(result.stdout)
        self.assertEqual(data["new_count"], 1)
        self.assertEqual(self._log("condensed", base), ["P1: Build"])
        self.assertEqual(
            subprocess.run(
                ["git", "show", "condensed:app.py"],
                cwd=self.tmp,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            ).stdout,
            "ok\n",
        )
        tree = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "condensed"],
            cwd=self.tmp,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout
        self.assertNotIn("plans/valid-plan", tree)
        diff = subprocess.run(
            ["git", "diff", "--quiet", "condensed", "HEAD", "--", ".", ":(exclude)plans"],
            cwd=self.tmp,
        )
        self.assertEqual(diff.returncode, 0)

    def test_condense_keeps_plans_and_rewrites_hashes(self) -> None:
        base = init_git(self.tmp)
        plan_dir, phase = self._done_phase()
        result = run_cli(
            self.tmp,
            "condense",
            str(plan_dir),
            "--base",
            base,
            "--branch",
            "condensed",
            "--plans",
            "keep",
            "--json",
        )
        self.assert_ok(result)
        data = json.loads(result.stdout)
        phase_commit = next(
            item["new"] for item in data["commits"] if item["kind"] == "phase"
        )
        plan_text = subprocess.run(
            [
                "git",
                "show",
                "condensed:plans/valid-plan/phases/01-build/plan.md",
            ],
            cwd=self.tmp,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout
        new_short = subprocess.run(
            ["git", "rev-parse", "--short", phase_commit],
            cwd=self.tmp,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
        self.assertIn(f"- Commit: {new_short}", plan_text)
        self.assertNotIn(f"- Commit: {phase}", plan_text)
        diff = subprocess.run(
            ["git", "diff", "--quiet", "condensed", "HEAD", "--", ".", ":(exclude)plans"],
            cwd=self.tmp,
        )
        self.assertEqual(diff.returncode, 0)

    def test_condense_keeps_a_mechanical_commit(self) -> None:
        base = init_git(self.tmp)
        (self.tmp / "format.txt").write_text("formatted\n", encoding="utf-8")
        format_commit = self._commit("style: format")
        plan_dir, _phase = self._done_phase()
        result = run_cli(
            self.tmp,
            "condense",
            str(plan_dir),
            "--base",
            base,
            "--branch",
            "condensed",
            "--plans",
            "drop",
            "--keep",
            format_commit,
        )
        self.assert_ok(result)
        self.assertEqual(
            self._log("condensed", base), ["style: format", "P1: Build"]
        )

    def test_condense_refuses_history_keep(self) -> None:
        init_git(self.tmp)
        plan_dir, _phase = self._done_phase()
        master = (plan_dir / "master.md").read_text(encoding="utf-8")
        master = master.replace(
            "- Branch: `plan/valid-plan`",
            "- Branch: `plan/valid-plan`\n- History: keep",
            1,
        )
        (plan_dir / "master.md").write_text(master, encoding="utf-8")
        self._commit("plan: history")
        result = run_cli(self.tmp, "condense", str(plan_dir))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("History: keep", result.stdout + result.stderr)

    def test_condense_refuses_dirty_tree(self) -> None:
        init_git(self.tmp)
        plan_dir, _phase = self._done_phase()
        (self.tmp / "app.py").write_text("dirty\n", encoding="utf-8")
        result = run_cli(self.tmp, "condense", str(plan_dir))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("working tree is not clean", result.stdout + result.stderr)


class ResumeAndReportTests(PlanTestCase):
    def test_resume_reports_branch_mismatch(self) -> None:
        init_git(self.tmp)
        make_valid_plan(self.tmp, "in_progress")
        result = subprocess.run(
            [sys.executable, str(RESUME), "plans/valid-plan", "--json"],
            cwd=self.tmp,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(
            any("master records branch" in warning for warning in report["warnings"])
        )

    def test_resume_prefers_in_progress_over_brief(self) -> None:
        master = """## Phase map

| ID | Phase | Outcome | Depends on | Status | Plan |
|---|---|---|---|---|---|
| P1 | One | x | none | done | p1 |
| P2 | Two | y | P1 | in_progress | p2 |

## Resume brief

- Current phase: P1
"""
        rows = planlib.phase_rows(master)
        self.assertEqual(planlib.current_phase_id(master, rows), "P2")

    def test_scope_reports_out_of_scope(self) -> None:
        init_git(self.tmp)
        plan_dir = make_valid_plan(self.tmp, "in_progress")
        (self.tmp / "app.py").write_text("ok\n", encoding="utf-8")
        (self.tmp / "other.py").write_text("no\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.tmp, check=True)
        subprocess.run(["git", "commit", "-qm", "P1: files"], cwd=self.tmp, check=True)
        result = run_cli(
            self.tmp,
            "scope",
            str(plan_dir),
            "P1",
            "--base",
            "HEAD~1",
            "--json",
        )
        self.assert_ok(result)
        data = json.loads(result.stdout)
        self.assertEqual(data["out_of_scope"], ["other.py"])

    def test_report_contains_sections(self) -> None:
        make_valid_plan(self.tmp, "ready")
        result = run_cli(self.tmp, "report", "plans/valid-plan")
        self.assert_ok(result)
        self.assertIn("# Valid Plan", result.stdout)
        self.assertIn("## Issue", result.stdout)
        self.assertIn("## Definition of done", result.stdout)
        self.assertIn("## What was done", result.stdout)
        self.assertIn("## Decisions", result.stdout)
        self.assertIn("| P1 |", result.stdout)
        self.assertIn("## Validation", result.stdout)

    def test_templates_match_required_headings(self) -> None:
        master_template = (
            ROOT
            / "skills"
            / "progressive-plan"
            / "references"
            / "master-template.md"
        ).read_text(encoding="utf-8")
        phase_template = (
            ROOT
            / "skills"
            / "progressive-plan"
            / "references"
            / "phase-plan-template.md"
        ).read_text(encoding="utf-8")
        for heading in planlib.MASTER_HEADINGS:
            self.assertTrue(
                planlib.has_heading(master_template, heading),
                f"master template missing {heading}",
            )
        for heading in planlib.PHASE_HEADINGS:
            self.assertTrue(
                planlib.has_heading(phase_template, heading),
                f"phase template missing {heading}",
            )
        small_master_template = (
            ROOT
            / "skills"
            / "progressive-plan"
            / "references"
            / "master-template-small.md"
        ).read_text(encoding="utf-8")
        small_phase_template = (
            ROOT
            / "skills"
            / "progressive-plan"
            / "references"
            / "phase-plan-template-small.md"
        ).read_text(encoding="utf-8")
        for heading in planlib.MASTER_HEADINGS:
            self.assertTrue(
                planlib.has_heading(small_master_template, heading),
                f"small master template missing {heading}",
            )
        for heading in planlib.PHASE_HEADINGS:
            self.assertTrue(
                planlib.has_heading(small_phase_template, heading),
                f"small phase template missing {heading}",
            )
        self.assertIn("Risks and unknowns", planlib.PHASE_HEADINGS)


class ValidationCharacterizationTests(PlanTestCase):
    def test_new_plan_draft_empty_phase_map(self) -> None:
        plan_dir = self.new_plan()
        self.assertEqual(
            planlib.validate_plan(plan_dir),
            {"errors": [], "warnings": ["master: phase map is empty"]},
        )

    def test_valid_plan_ready(self) -> None:
        plan_dir = make_valid_plan(self.tmp, "ready")
        self.assertEqual(
            planlib.validate_plan(plan_dir),
            {"errors": [], "warnings": []},
        )

    def test_valid_plan_in_progress(self) -> None:
        plan_dir = make_valid_plan(self.tmp, "in_progress")
        self.assertEqual(
            planlib.validate_plan(plan_dir),
            {"errors": [], "warnings": []},
        )

    def test_malformed_phase_row(self) -> None:
        plan_dir = self.new_plan()
        master = self.master(plan_dir)
        lines = master.splitlines()
        index = next(
            i for i, line in enumerate(lines) if line.startswith("| ID | Phase |")
        )
        lines.insert(index + 2, "| P1 | Broken | no plan |")
        (plan_dir / "master.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
        self.assertEqual(
            planlib.validate_plan(plan_dir),
            {
                "errors": [
                    "master: malformed phase row for P1; expected 6 columns (ID, Phase, Outcome, Depends on, Status, Plan)",
                    "master: P1 has invalid status ''",
                ],
                "warnings": [],
            },
        )

    def test_malformed_ledger_row(self) -> None:
        plan_dir = self.new_plan()
        master = self.master(plan_dir)
        lines = master.splitlines()
        index = next(
            i
            for i, line in enumerate(lines)
            if line.startswith("| ID | Date | Phase | Affects |")
        )
        lines.insert(
            index + 2,
            "| L1 | 2026-11-14 | P1 | P99 | Found | bogus |  | open |",
        )
        (plan_dir / "master.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
        self.assertEqual(
            planlib.validate_plan(plan_dir),
            {
                "errors": [
                    "master: ledger L1 affects unknown phase P99",
                    "master: ledger L1 has invalid type 'bogus'",
                    "master: ledger L1 has no action taken",
                    "master: ledger L1 names unknown phase 'P1'",
                ],
                "warnings": ["master: phase map is empty"],
            },
        )


if __name__ == "__main__":
    unittest.main()
