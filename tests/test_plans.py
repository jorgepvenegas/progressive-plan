from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "progressive-plan" / "scripts" / "progressive_plan.py"
RESUME = ROOT / "skills" / "plan-resume" / "scripts" / "resume_status.py"
sys.path.insert(0, str(ROOT / "skills" / "progressive-plan" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import planlib  # noqa: E402
from fixtures import init_git, make_valid_plan, valid_plan  # noqa: E402


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


class ScaffoldTests(PlanTestCase):
    def test_new_records_root_and_size(self) -> None:
        plan_dir = self.new_plan()
        master = self.master(plan_dir)
        self.assertIn("Size: small", master)
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


class CommitAndCloseTests(PlanTestCase):
    def test_record_commit_rejects_wrong_head_subject(self) -> None:
        init_git(self.tmp)
        make_valid_plan(self.tmp, "in_progress")
        result = run_cli(
            self.tmp, "record-commit", "plans/valid-plan", "P1", "--by", "worker-1"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not look like the P1 commit", result.stdout + result.stderr)

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
        head = init_git(self.tmp)
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


if __name__ == "__main__":
    unittest.main()
