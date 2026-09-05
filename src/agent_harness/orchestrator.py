from __future__ import annotations
import subprocess
from dataclasses import dataclass
from pathlib import Path
from .context import context_hash
from .diagnostics import summarize_provider_failure
from .domain import ScopeBudget, TaskIntake, TaskState, TaskStatement
from .evidence import EvidenceEnvelope
from .execution_manager import ExecutionManager
from .gates import GateEngine
from .git_workspace import GitWorkspaceManager
from .policy import Slice0Policy
from .provider import AgentProvider, ProviderAttempt
from .retry_policy import retry_denial_reason
from .scope import evaluate_scope
from .store import HarnessStore
from .supervision_checkpoints import SupervisionPort, checkpoint_for_provider_outcome
from .trusted_runner import TrustedRunner
from .verification import inspect_verification_surface

@dataclass(frozen=True, slots=True)
class Slice0Result:
    task_id: str
    state: TaskState
    ready: bool
    evidence_id: str | None
    failures: tuple[str, ...]
    summary: str

class Slice0Orchestrator:
    def __init__(self, *, store: HarnessStore, provider: AgentProvider, runtime_root: str | Path, provider_timeout_s: float, verification_timeout_s: float, max_attempts: int = 1, supervision: SupervisionPort | None = None) -> None:
        if max_attempts < 1: raise ValueError("max_attempts must be at least 1")
        self.store=store; self.provider=provider; self.runtime_root=Path(runtime_root).resolve(); self.runtime_root.mkdir(parents=True,exist_ok=True)
        self.provider_timeout_s=provider_timeout_s; self.verification_timeout_s=verification_timeout_s; self.max_attempts=max_attempts
        self.gates=GateEngine(policy=Slice0Policy()); self.lifecycle=ExecutionManager(store=store,supervision=supervision)

    def run(self, *, repo_path: str | Path, statement: TaskStatement, acceptance: tuple[str,...], constraints: tuple[str,...], scope: ScopeBudget, verification_justification: str | None = None) -> Slice0Result:
        repo=Path(repo_path).resolve(); base_sha=self._git(repo,"rev-parse","HEAD").strip()
        intake=TaskIntake.create(statement=statement,acceptance=acceptance,constraints=constraints,scope=scope)
        task_id=self.lifecycle.begin(intake=intake,base_sha=base_sha); task_context_hash=context_hash(intake)
        workspace=GitWorkspaceManager(repo_path=repo,runtime_root=self.runtime_root); writer=workspace.create_writer_worktree(task_id=task_id,base_sha=base_sha)
        attempt=0; previous_head_sha=None; previous_failures=(); previous_evidence_id=None
        while True:
            attempt += 1; run_id=self.store.create_run(task_id); provider_result=self.provider.execute(intake,writer,timeout_s=self.provider_timeout_s)
            head_sha=workspace.candidate_head(writer)
            self.store.record_provider_attempt(ProviderAttempt.from_result(task_id=task_id,run_id=run_id,provider_id=self.provider.provider_id,attempt_number=attempt,result=provider_result,candidate_sha=None if head_sha==base_sha else head_sha),context_hash=task_context_hash)
            if provider_result.timed_out:
                self.lifecycle.provider_timed_out(task_id); self.store.finish_run(run_id,state=TaskState.INTERRUPTED.value)
                return self._result(task_id=task_id,state=TaskState.INTERRUPTED,evidence_id=previous_evidence_id,failures=("provider_timeout",),changed="No candidate commit was accepted.",why="The provider exceeded its explicit deadline and was terminated.",evidence=f"No trusted verification was run. Provider diagnostic (not evidence):\n{summarize_provider_failure(provider_result)}",decision="The task can be resumed or reassigned later; no irreversible action occurred.")
            if checkpoint_for_provider_outcome(provider_result.outcome) is not None:
                self.lifecycle.provider_unavailable(task_id,outcome=provider_result.outcome,provider_result=provider_result); self.store.finish_run(run_id,state=TaskState.BLOCKED.value)
                return self._result(task_id=task_id,state=TaskState.BLOCKED,evidence_id=previous_evidence_id,failures=(f"provider_unavailable:{provider_result.outcome.value}",),changed="No candidate was accepted.",why=f"The provider ended as {provider_result.outcome.value}, so it never reached the task.",evidence=f"No trusted verification was run. Provider diagnostic (not evidence):\n{summarize_provider_failure(provider_result)}",decision="Whether and when to try again is a governed decision.")
            if provider_result.exit_code != 0:
                self.lifecycle.provider_failed(task_id); self.store.finish_run(run_id,state=TaskState.FAILED.value)
                return self._result(task_id=task_id,state=TaskState.FAILED,evidence_id=previous_evidence_id,failures=("provider_failed",),changed="No candidate was accepted.",why=f"The provider exited with code {provider_result.exit_code}, classified as {provider_result.outcome.value}.",evidence=f"No trusted verification was run. Provider diagnostic (not evidence):\n{summarize_provider_failure(provider_result)}",decision="No human decision is required; execution failed safely.")
            if head_sha == base_sha:
                self.lifecycle.provider_failed(task_id); self.store.finish_run(run_id,state=TaskState.FAILED.value)
                return self._result(task_id=task_id,state=TaskState.FAILED,evidence_id=None,failures=("provider_created_no_candidate_commit",),changed="No committed candidate differs from the base.",why="Trusted verification only evaluates committed candidate state.",evidence=f"No verification checkout was created. Provider diagnostic (not evidence):\n{summarize_provider_failure(provider_result)}",decision="No irreversible action occurred.")
            if head_sha == previous_head_sha:
                self.lifecycle.no_progress(task_id); self.store.finish_run(run_id,state=TaskState.BLOCKED.value)
                return self._result(task_id=task_id,state=TaskState.BLOCKED,evidence_id=previous_evidence_id,failures=previous_failures+("no_progress_detected",),changed=f"Attempt {attempt} left candidate {head_sha[:12]} unchanged.",why="A retry that cannot move the candidate cannot move the verdict.",evidence="Trusted verification was not repeated for an unchanged candidate.",decision="Change the goal, scope, or provider deliberately before another run.")
            self.lifecycle.candidate_produced(task_id,head_sha=head_sha)
            verify=workspace.create_verification_checkout(head_sha=head_sha,run_id=run_id)
            runner=TrustedRunner(evidence_root=self.runtime_root/"evidence"/task_id,trusted_hooks_path=workspace.trusted_hooks)
            rev_result=runner.run("git_rev_parse",cwd=verify,timeout_s=self.verification_timeout_s); verification_head_sha=""
            if rev_result.exit_code == 0 and not rev_result.timed_out: verification_head_sha=rev_result.stdout_path.read_text(encoding="utf-8").strip()
            surface=inspect_verification_surface(repo_path=repo,base_sha=base_sha,head_sha=head_sha,justification=verification_justification)
            changed_loc,unmeasurable_paths=self._diff_stats(repo,base_sha,head_sha)
            scope_report=evaluate_scope(changed_paths=surface.changed_paths,changed_loc=changed_loc,budget=scope,unmeasurable_paths=unmeasurable_paths)
            pytest_result=runner.run("pytest",cwd=verify,timeout_s=self.verification_timeout_s)
            evidence=EvidenceEnvelope.from_runner(task_id=task_id,run_id=run_id,goal_hash=intake.goal_hash,acceptance_hash=intake.acceptance_hash,scope_budget_hash=intake.scope_budget_hash,repo=str(repo),base_sha=base_sha,head_sha=head_sha,verification_checkout=str(verify),verification_surface=surface,runner=pytest_result,verification_head_sha=verification_head_sha)
            evidence_id=self.store.record_evidence(task_id=task_id,run_id=run_id,metadata=evidence.to_metadata())
            gate=self.gates.evaluate(task=self.store.get_task(task_id),expected_intake=intake,evidence=evidence,scope_report=scope_report,agent_claim=provider_result.stdout)
            evidence_text=f"Trusted pytest exit={pytest_result.exit_code}; verification HEAD={verification_head_sha[:12] or 'unavailable'}; evidence_id={evidence_id}."
            if gate.ready:
                self.lifecycle.gates_passed(task_id,evidence_refs=(evidence_id,)); self.store.finish_run(run_id,state=TaskState.READY.value)
                return self._result(task_id=task_id,state=TaskState.READY,evidence_id=evidence_id,failures=gate.failures,changed=f"Candidate {head_sha[:12]} was produced in an isolated writer worktree on attempt {attempt} of at most {self.max_attempts}.",why="Readiness is determined by committed state and deterministic gates, not provider claims.",evidence=evidence_text,decision="Review the candidate; merge remains a human gate.")
            if attempt >= self.max_attempts:
                failures=gate.failures + (("retry_budget_exhausted",) if attempt > 1 else ())
                self.lifecycle.gates_failed(task_id,retrying=False,gate_failures=failures,evidence_refs=(evidence_id,)); self.store.finish_run(run_id,state=TaskState.BLOCKED.value)
                return self._result(task_id=task_id,state=TaskState.BLOCKED,evidence_id=evidence_id,failures=failures,changed=f"Candidate {head_sha[:12]} was produced in an isolated writer worktree on attempt {attempt} of at most {self.max_attempts}.",why="Readiness is determined by committed state and deterministic gates, not provider claims.",evidence=evidence_text,decision="Resolve the listed gate failures before any human-gated action.")
            denial=retry_denial_reason(provider_result.outcome)
            if denial is not None:
                self.lifecycle.retry_refused(task_id); self.store.finish_run(run_id,state=TaskState.BLOCKED.value)
                return self._result(task_id=task_id,state=TaskState.BLOCKED,evidence_id=evidence_id,failures=gate.failures+(denial,),changed=f"Candidate {head_sha[:12]} did not pass gates on attempt {attempt}.",why=f"The attempt ended as {provider_result.outcome.value}; automatic repetition is not authorized.",evidence=evidence_text,decision="Classify or deliberately rerun the task.")
            self.store.finish_run(run_id,state=TaskState.RUNNING.value); previous_head_sha=head_sha; previous_failures=gate.failures; previous_evidence_id=evidence_id; self.lifecycle.gates_failed(task_id,retrying=True)

    @staticmethod
    def _git(repo: Path,*args: str) -> str:
        completed=subprocess.run(["git","-C",str(repo),*args],text=True,capture_output=True,check=False)
        if completed.returncode != 0: raise RuntimeError(completed.stderr.strip() or "git command failed")
        return completed.stdout
    @classmethod
    def _diff_stats(cls, repo: Path, base_sha: str, head_sha: str) -> tuple[int,tuple[str,...]]:
        output=cls._git(repo,"diff","--numstat","--no-renames",base_sha,head_sha); total=0; unmeasurable=[]
        for line in output.splitlines():
            if not line.strip(): continue
            added,deleted,path=line.split("\t",2)
            if added=="-" or deleted=="-": unmeasurable.append(path); continue
            total += int(added)+int(deleted)
        return total,tuple(unmeasurable)
    @staticmethod
    def _result(*,task_id: str,state: TaskState,evidence_id: str | None,failures: tuple[str,...],changed: str,why: str,evidence: str,decision: str) -> Slice0Result:
        failure_text=", ".join(failures) if failures else "none"
        summary=f"Result\n{state.value}\n\nWhat changed\n{changed}\n\nWhy\n{why}\n\nEvidence\n{evidence}\nGate failures: {failure_text}\n\nWhat you learned\nThe provider's own PASS/ready text has no authority; the Trusted Runner and Gate Engine decide.\n\nWhat requires your decision, if anything\n{decision}"
        return Slice0Result(task_id,state,state is TaskState.READY,evidence_id,failures,summary)
