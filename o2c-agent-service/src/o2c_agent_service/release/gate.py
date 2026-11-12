"""AI-DLC release gate for this service: E2A BasePipeline with real checks.

run_pipeline() (inherited, public) runs the seven fixed stages in order and stops at the
first failure:
  static_security       secret patterns in the service's files
  test_execution        pytest
  scaffold_compliance   capacity equation + E2A's Governed Entry Point rules (e2a.conformance,
                        strict: R1 framework-owned method overridden, R2 protected hook called
                        from outside, D1 deprecated hook)
  ragas_gate            golden questions: right policy retrieved AND a grounded answer
  artifact_compilation  byte-compiles the package (the image is built by the Dockerfile)
  dynamic_security      red-team prompts against the running assistant (in-process)
  deployment_rollout    no live deployment: records that Terraform is tested in CI
Usage:  poetry run python -m o2c_agent_service.release.gate [--skip-tests] [--report FILE]
"""
import argparse
import compileall
import json
import re
import subprocess
import sys
from pathlib import Path

from e2a_base import BasePipeline

from ..services.assistant import Forbidden, O2CAssistant
from ..services.llm import build_o2c_llm
from .fakes import FakeReconciliationService, FakeSettlementService

ROOT = Path(__file__).resolve().parents[3]
SECRETS = [re.compile(p) for p in (r"AKIA[0-9A-Z]{16}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
                                   r"gh[pousr]_[A-Za-z0-9]{36}", r"AIza[0-9A-Za-z_-]{35}",
                                   r"(?i)(api[_-]?key|password|secret)\s*[:=]\s*['\"][^'\"]{8,}['\"]")]
def build_assistant() -> O2CAssistant:
    return O2CAssistant(ROOT, build_o2c_llm(), "http://settlement.test", "http://reconciliation.test",
                        FakeSettlementService().transport(), FakeReconciliationService().transport())


class O2CReleaseGate(BasePipeline):
    def __init__(self, root: Path = ROOT, run_tests: bool = True) -> None:
        super().__init__()
        self.root, self.run_tests = Path(root), run_tests
        self.required_artifact_matrix = ["o2c-agent-service"]
        self.conformance_paths = (str(self.root / "src"),)
        self.evidence = {}

    def _files(self, *patterns):
        for folder in ("src", "policies", "knowledge", "infra", "evals"):
            for pattern in patterns:
                yield from (self.root / folder).rglob(pattern)

    def _run_static_security_scans(self, config, **kwargs) -> bool:
        hits = [f"{p.relative_to(self.root)}: {rx.pattern}" for p in self._files("*.py", "*.yaml", "*.tf", "*.md",
                                                                               "*.json")
                for rx in SECRETS if rx.search(p.read_text(encoding="utf-8", errors="ignore"))]
        self.evidence["secrets"] = hits
        return not hits

    def _execute_test_suite(self, config, **kwargs) -> bool:
        if not self.run_tests:
            self.evidence["tests"] = "skipped (--skip-tests): CI runs pytest in its own step"
            return True
        done = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=self.root, capture_output=True, text=True)
        self.evidence["tests"] = done.stdout.strip().splitlines()[-1:] or done.stderr[-300:]
        return done.returncode == 0

    def _verify_scaffold_contracts(self, config, **kwargs) -> bool:
        """E2A's default check (e2a.conformance) over src/, strict: this service has no
        R2 or D1 findings to tolerate."""
        ok = super()._verify_scaffold_contracts(config, conformance_strict=True, **kwargs)
        self.evidence["entry_point_findings"] = [str(f) for f in self.conformance_findings]
        return ok

    def _run_rag_eval(self, config, **kwargs) -> float:
        assistant = build_assistant()
        golden = json.loads((self.root / "evals" / "golden.json").read_text(encoding="utf-8"))
        rows = []
        for case in golden:
            answer = assistant.handle(case["question"], "acme", "gate", "viewer")
            expected = case["expected_policy"]
            if expected is None:                         # must decline, not invent
                score = 1.0 if (answer.degraded and not answer.citations) else 0.0
            else:
                score = 1.0 if (expected in answer.citations and not answer.degraded) else 0.0
            rows.append({"question": case["question"], "expected": expected, "cited": answer.citations,
                         "score": score})
        self.evidence["rag_eval"] = rows
        return sum(r["score"] for r in rows) / len(rows)

    def _compile_artifact(self, artifact_name, config, **kwargs) -> bool:
        return compileall.compile_dir(str(self.root / "src"), quiet=1)

    def _run_dynamic_security_checks(self, config, **kwargs) -> bool:
        assistant = build_assistant()
        cases = json.loads((self.root / "evals" / "redteam.json").read_text(encoding="utf-8"))
        failures = []
        for text in cases["injections"]:
            if assistant.handle(text, "acme", "redteam", "sales").status != "REFUSED":
                failures.append(f"not refused: {text}")
        for case in cases["pii"]:
            answer = assistant.handle(case["text"], "acme", "redteam", "sales").answer
            failures += [f"leaked {s}" for s in case["must_not_contain"] if s in answer]
        for case in cases["entitlements"]:
            try:
                assistant.handle(case["text"], "acme", "redteam", case["role"])
                failures.append(f"role {case['role']} was not refused")
            except Forbidden:
                pass
        self.evidence["dynamic_security"] = failures
        return not failures

    def _execute_deployment_rollout(self, strategy, config, **kwargs) -> dict:
        return {"deployed": False, "strategy": strategy,
                "note": "no live deployment: Cloud Run Terraform is tested with a mock provider in CI"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--report", default="release-gate-report.json")
    args = parser.parse_args(argv)
    gate = O2CReleaseGate(run_tests=not args.skip_tests)
    report = gate.run_pipeline({"fleet_replica_count": 1})
    report.pop("message_log", None)
    report["evidence"] = gate.evidence
    Path(args.report).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "stages", "rag_eval_score") if k in report}, indent=2))
    if report["status"] != "SUCCESS":
        print("FAILED:", report.get("error"))
    return 0 if report["status"] == "SUCCESS" else 1


if __name__ == "__main__":
    sys.exit(main())
