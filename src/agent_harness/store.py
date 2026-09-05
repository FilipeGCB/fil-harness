from __future__ import annotations
import json, sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from .canonical import canonical_json
from .domain import ScopeBudget, TaskIntake, TaskState, TaskStatement, transition_allowed
from .provider import ProviderAttempt, ProviderOutcome
from .supervision_checkpoints import TERMINAL_VERDICTS

class StoreError(RuntimeError): pass
class TaskNotFoundError(StoreError): pass
class IllegalTransitionError(StoreError): pass

@dataclass(frozen=True, slots=True)
class PersistedTask:
    task_id: str; state: TaskState; goal: str; goal_hash: str; acceptance_hash: str; constraints_hash: str; scope_budget_hash: str; base_sha: str; head_sha: str | None
@dataclass(frozen=True, slots=True)
class PersistedAttempt:
    attempt_id: str; task_id: str; run_id: str | None; provider_id: str; attempt_number: int; outcome: ProviderOutcome; exit_code: int | None; candidate_sha: str | None; context_hash: str; started_at: str; ended_at: str
@dataclass(frozen=True, slots=True)
class PersistedSupervisionRequest:
    request_id: str; task_id: str; checkpoint: str; status: str; payload: dict[str, object]; external_ref: str | None
@dataclass(frozen=True, slots=True)
class OpenedSupervisionRequest:
    request: PersistedSupervisionRequest; created: bool
@dataclass(frozen=True, slots=True)
class PersistedSupervisionDecision:
    decision_id: str; request_id: str; actor: str; decision: str; action_type: str | None; payload: dict[str, object]; external_comment_id: str | None

def _utc_now() -> str: return datetime.now(timezone.utc).isoformat()

class HarnessStore:
    def __init__(self, path: str | Path, *, busy_timeout_ms: int = 5000) -> None:
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path); self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL"); self._conn.execute("PRAGMA foreign_keys = ON"); self._conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
        self._create_schema()

    def _create_schema(self) -> None:
        self._conn.executescript('''
        CREATE TABLE IF NOT EXISTS tasks (task_id TEXT PRIMARY KEY,state TEXT NOT NULL,goal TEXT NOT NULL,statement_json TEXT,acceptance_json TEXT NOT NULL,constraints_json TEXT NOT NULL,scope_json TEXT NOT NULL,goal_hash TEXT NOT NULL,acceptance_hash TEXT NOT NULL,constraints_hash TEXT NOT NULL,scope_budget_hash TEXT NOT NULL,base_sha TEXT NOT NULL,head_sha TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (session_id TEXT PRIMARY KEY,task_id TEXT NOT NULL REFERENCES tasks(task_id),provider TEXT NOT NULL,external_session_id TEXT,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY,task_id TEXT NOT NULL REFERENCES tasks(task_id),state TEXT NOT NULL,started_at TEXT NOT NULL,ended_at TEXT);
        CREATE TABLE IF NOT EXISTS events (event_id INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT NOT NULL REFERENCES tasks(task_id),event_type TEXT NOT NULL,payload_json TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS evidence (evidence_id TEXT PRIMARY KEY,task_id TEXT NOT NULL REFERENCES tasks(task_id),run_id TEXT,metadata_json TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS provider_attempts (attempt_id TEXT PRIMARY KEY,task_id TEXT NOT NULL REFERENCES tasks(task_id),run_id TEXT,provider_id TEXT NOT NULL,attempt_number INTEGER NOT NULL,outcome TEXT NOT NULL,exit_code INTEGER,candidate_sha TEXT,context_hash TEXT NOT NULL,started_at TEXT NOT NULL,ended_at TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS supervision_requests (request_id TEXT PRIMARY KEY,task_id TEXT NOT NULL REFERENCES tasks(task_id),checkpoint TEXT NOT NULL,status TEXT NOT NULL,payload_json TEXT NOT NULL,external_ref TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS supervision_decisions (decision_id TEXT PRIMARY KEY,request_id TEXT NOT NULL REFERENCES supervision_requests(request_id),actor TEXT NOT NULL,decision TEXT NOT NULL,action_type TEXT,payload_json TEXT NOT NULL,external_comment_id TEXT,created_at TEXT NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_supervision_decisions_external_comment ON supervision_decisions(external_comment_id) WHERE external_comment_id IS NOT NULL;
        ''')
        self._migrate_tasks_statement()
        self._migrate_supervision_applied_verdict()
        self._conn.commit()

    def _migrate_tasks_statement(self) -> None:
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(tasks)")}
        if "statement_json" not in columns:
            self._conn.execute("ALTER TABLE tasks ADD COLUMN statement_json TEXT")

    def _migrate_supervision_applied_verdict(self) -> None:
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(supervision_requests)")}
        if "applied_verdict" not in columns:
            self._conn.execute("ALTER TABLE supervision_requests ADD COLUMN applied_verdict TEXT")

    def pragma(self, name: str):
        if name not in {"journal_mode","foreign_keys","busy_timeout"}: raise ValueError(f"unsupported pragma: {name}")
        row = self._conn.execute(f"PRAGMA {name}").fetchone()
        if row is None: raise StoreError(f"pragma returned no value: {name}")
        return row[0]

    def create_task(self, *, intake: TaskIntake, base_sha: str) -> str:
        task_id = str(uuid4()); now = _utc_now(); scope_payload={"allowed_paths": intake.scope.allowed_paths,"max_files":intake.scope.max_files,"max_loc":intake.scope.max_loc}
        with self._conn:
            self._conn.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(task_id,TaskState.PENDING.value,intake.goal,canonical_json(intake.statement.as_payload()),canonical_json(intake.acceptance),canonical_json(intake.constraints),canonical_json(scope_payload),intake.goal_hash,intake.acceptance_hash,intake.constraints_hash,intake.scope_budget_hash,base_sha,None,now,now))
            self._append_event(task_id,"TASK_CREATED",{"state":TaskState.PENDING.value},now)
        return task_id

    def get_task_intake(self, task_id: str) -> TaskIntake:
        row=self._conn.execute("SELECT statement_json,acceptance_json,constraints_json,scope_json FROM tasks WHERE task_id=?",(task_id,)).fetchone()
        if row is None: raise TaskNotFoundError(task_id)
        if row["statement_json"] is None:
            raise StoreError(
                f"task {task_id} has no typed statement; it predates the intake contract "
                "and its intent cannot be inferred"
            )
        scope=json.loads(row["scope_json"])
        return TaskIntake.create(statement=TaskStatement.from_payload(json.loads(row["statement_json"])),acceptance=tuple(json.loads(row["acceptance_json"])),constraints=tuple(json.loads(row["constraints_json"])),scope=ScopeBudget(tuple(scope["allowed_paths"]),scope["max_files"],scope["max_loc"]))

    def get_task(self, task_id: str) -> PersistedTask:
        row=self._conn.execute("SELECT task_id,state,goal,goal_hash,acceptance_hash,constraints_hash,scope_budget_hash,base_sha,head_sha FROM tasks WHERE task_id=?",(task_id,)).fetchone()
        if row is None: raise TaskNotFoundError(task_id)
        return PersistedTask(row["task_id"],TaskState(row["state"]),row["goal"],row["goal_hash"],row["acceptance_hash"],row["constraints_hash"],row["scope_budget_hash"],row["base_sha"],row["head_sha"])

    def transition_task(self, task_id: str, target: TaskState) -> None:
        current=self.get_task(task_id)
        if not transition_allowed(current.state,target): raise IllegalTransitionError(f"illegal task transition: {current.state.value} -> {target.value}")
        now=_utc_now()
        with self._conn:
            cursor=self._conn.execute("UPDATE tasks SET state=?,updated_at=? WHERE task_id=? AND state=?",(target.value,now,task_id,current.state.value))
            if cursor.rowcount != 1: raise StoreError("task state changed concurrently")
            self._append_event(task_id,"STATE_TRANSITION",{"from":current.state.value,"to":target.value},now)

    def set_head_sha(self, task_id: str, head_sha: str) -> None:
        current=self.get_task(task_id)
        if current.state is not TaskState.RUNNING: raise StoreError("candidate head can only be set while RUNNING")
        normalized=head_sha.strip()
        if not normalized: raise ValueError("head_sha must not be empty")
        now=_utc_now()
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE tasks SET head_sha=?,updated_at=? WHERE task_id=? AND state=?",
                (normalized,now,task_id,TaskState.RUNNING.value),
            )
            if cursor.rowcount != 1:
                raise StoreError("task state changed concurrently")
            self._append_event(task_id,"CANDIDATE_HEAD_SET",{"head_sha":normalized},now)

    def create_run(self, task_id: str, *, state: str = "RUNNING") -> str:
        self.get_task(task_id); run_id=str(uuid4()); now=_utc_now()
        with self._conn: self._conn.execute("INSERT INTO runs VALUES (?,?,?,?,NULL)",(run_id,task_id,state,now))
        return run_id

    def finish_run(self, run_id: str, *, state: str) -> None:
        with self._conn:
            cursor=self._conn.execute("UPDATE runs SET state=?,ended_at=? WHERE run_id=?",(state,_utc_now(),run_id))
            if cursor.rowcount != 1: raise StoreError(f"run not found: {run_id}")

    def record_provider_attempt(self, attempt: ProviderAttempt, *, context_hash: str) -> None:
        self.get_task(attempt.task_id); now=_utc_now()
        with self._conn:
            self._conn.execute("INSERT INTO provider_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",(attempt.attempt_id,attempt.task_id,attempt.run_id,attempt.provider_id,attempt.attempt_number,attempt.outcome.value,attempt.exit_code,attempt.candidate_sha,context_hash,attempt.started_at,attempt.ended_at,now))
            self._append_event(attempt.task_id,"PROVIDER_ATTEMPT_RECORDED",{"attempt_id":attempt.attempt_id,"attempt_number":attempt.attempt_number,"provider_id":attempt.provider_id,"outcome":attempt.outcome.value},now)

    def get_provider_attempts(self, task_id: str) -> tuple[PersistedAttempt,...]:
        rows=self._conn.execute("SELECT attempt_id,task_id,run_id,provider_id,attempt_number,outcome,exit_code,candidate_sha,context_hash,started_at,ended_at FROM provider_attempts WHERE task_id=? ORDER BY attempt_number,created_at",(task_id,)).fetchall()
        return tuple(PersistedAttempt(r["attempt_id"],r["task_id"],r["run_id"],r["provider_id"],r["attempt_number"],ProviderOutcome(r["outcome"]),r["exit_code"],r["candidate_sha"],r["context_hash"],r["started_at"],r["ended_at"]) for r in rows)

    def record_evidence(self, *, task_id: str, run_id: str | None, metadata: object) -> str:
        self.get_task(task_id); eid=str(uuid4()); now=_utc_now()
        with self._conn:
            self._conn.execute("INSERT INTO evidence VALUES (?,?,?,?,?)",(eid,task_id,run_id,canonical_json(metadata),now)); self._append_event(task_id,"EVIDENCE_RECORDED",{"evidence_id":eid,"run_id":run_id},now)
        return eid

    def get_evidence_metadata(self, evidence_id: str) -> dict[str,object]:
        row=self._conn.execute("SELECT metadata_json FROM evidence WHERE evidence_id=?",(evidence_id,)).fetchone()
        if row is None: raise StoreError(f"evidence not found: {evidence_id}")
        value=json.loads(row["metadata_json"])
        if not isinstance(value,dict): raise StoreError("evidence metadata must be an object")
        return value

    def create_supervision_request(self, *, request_id: str, task_id: str, checkpoint: str, payload: object) -> str:
        self.get_task(task_id)
        normalized_request_id = request_id.strip()
        normalized_checkpoint = checkpoint.strip()
        if not normalized_request_id:
            raise ValueError("request_id must not be empty")
        if not normalized_checkpoint:
            raise ValueError("checkpoint must not be empty")
        now = _utc_now()
        with self._conn:
            self._conn.execute(
                "INSERT INTO supervision_requests (request_id,task_id,checkpoint,status,payload_json,external_ref,created_at,updated_at) VALUES (?,?,?,'PENDING',?,NULL,?,?)",
                (normalized_request_id,task_id,normalized_checkpoint,canonical_json(payload),now,now),
            )
            self._append_event(task_id,"SUPERVISION_REQUEST_CREATED",{"request_id":normalized_request_id,"checkpoint":normalized_checkpoint},now)
        return normalized_request_id

    def open_supervision_request(self, *, request_id: str, task_id: str, checkpoint: str, payload: object) -> OpenedSupervisionRequest:
        existing=self.find_supervision_request(request_id)
        if existing is not None: return OpenedSupervisionRequest(existing,False)
        self.create_supervision_request(request_id=request_id, task_id=task_id, checkpoint=checkpoint, payload=payload)
        return OpenedSupervisionRequest(self.get_supervision_request(request_id),True)

    def get_supervision_request(self, request_id: str) -> PersistedSupervisionRequest:
        row=self._conn.execute("SELECT request_id,task_id,checkpoint,status,payload_json,external_ref FROM supervision_requests WHERE request_id=?",(request_id,)).fetchone()
        if row is None: raise StoreError(f"supervision request not found: {request_id}")
        payload=json.loads(row["payload_json"])
        return PersistedSupervisionRequest(row["request_id"],row["task_id"],row["checkpoint"],row["status"],payload,row["external_ref"])

    def find_supervision_request(self, request_id: str) -> PersistedSupervisionRequest | None:
        try: return self.get_supervision_request(request_id)
        except StoreError: return None

    def set_supervision_external_ref(self, request_id: str, external_ref: str) -> None:
        request = self.get_supervision_request(request_id)
        normalized = external_ref.strip()
        if not normalized:
            raise ValueError("external_ref must not be empty")
        if request.external_ref == normalized:
            return
        if request.external_ref is not None:
            raise StoreError("supervision request already has a different external_ref")
        now = _utc_now()
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE supervision_requests SET external_ref=?,updated_at=? WHERE request_id=? AND external_ref IS NULL",
                (normalized,now,request_id),
            )
            if cursor.rowcount != 1:
                raise StoreError("supervision request external_ref changed concurrently")
            self._append_event(request.task_id,"SUPERVISION_PUBLISHED",{"request_id":request_id,"external_ref":normalized},now)

    def set_supervision_status(self, request_id: str, status: str) -> None:
        request = self.get_supervision_request(request_id)
        normalized = status.strip()
        if not normalized:
            raise ValueError("status must not be empty")
        if request.status == normalized:
            return
        now = _utc_now()
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE supervision_requests SET status=?,updated_at=? WHERE request_id=?",
                (normalized,now,request_id),
            )
            if cursor.rowcount != 1:
                raise StoreError(f"supervision request not found: {request_id}")
            self._append_event(request.task_id,"SUPERVISION_STATUS_CHANGED",{"request_id":request_id,"from":request.status,"to":normalized},now)

    def record_supervision_decision(self, *, request_id: str, actor: str, decision: str, action_type: str | None, payload: object, external_comment_id: str | None = None) -> str:
        request = self.get_supervision_request(request_id)
        normalized_actor = actor.strip()
        normalized_decision = decision.strip()
        normalized_action = action_type.strip() if isinstance(action_type,str) and action_type.strip() else None
        normalized_external_id = external_comment_id.strip() if isinstance(external_comment_id,str) and external_comment_id.strip() else None
        if not normalized_actor:
            raise ValueError("actor must not be empty")
        if not normalized_decision:
            raise ValueError("decision must not be empty")
        if normalized_external_id is not None:
            existing = self._conn.execute(
                "SELECT decision_id FROM supervision_decisions WHERE external_comment_id=?",
                (normalized_external_id,),
            ).fetchone()
            if existing is not None:
                return str(existing["decision_id"])
        did = str(uuid4()); now = _utc_now()
        with self._conn:
            self._conn.execute(
                "INSERT INTO supervision_decisions (decision_id,request_id,actor,decision,action_type,payload_json,external_comment_id,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (did,request_id,normalized_actor,normalized_decision,normalized_action,canonical_json(payload),normalized_external_id,now),
            )
            self._conn.execute("UPDATE supervision_requests SET status='DECIDED',updated_at=? WHERE request_id=?",(now,request_id))
            self._append_event(request.task_id,"SUPERVISION_DECISION_RECORDED",{"request_id":request_id,"decision_id":did,"actor":normalized_actor,"decision":normalized_decision},now)
        return did

    def get_supervision_decisions(self, request_id: str) -> tuple[PersistedSupervisionDecision, ...]:
        self.get_supervision_request(request_id)
        rows = self._conn.execute(
            "SELECT decision_id,request_id,actor,decision,action_type,payload_json,external_comment_id FROM supervision_decisions WHERE request_id=? ORDER BY created_at,decision_id",
            (request_id,),
        ).fetchall()
        result: list[PersistedSupervisionDecision] = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            if not isinstance(payload,dict):
                raise StoreError("supervision decision payload must be an object")
            result.append(PersistedSupervisionDecision(
                decision_id=row["decision_id"], request_id=row["request_id"], actor=row["actor"],
                decision=row["decision"], action_type=row["action_type"], payload=payload,
                external_comment_id=row["external_comment_id"],
            ))
        return tuple(result)

    def claim_supervision_verdict(self, request_id: str, verdict: str) -> bool:
        request=self.get_supervision_request(request_id); now=_utc_now()
        with self._conn:
            cur=self._conn.execute("UPDATE supervision_requests SET applied_verdict=?,updated_at=? WHERE request_id=? AND (applied_verdict IS NULL OR applied_verdict != ?)",(verdict,now,request_id,verdict))
            if cur.rowcount != 1: return False
            self._append_event(request.task_id,"SUPERVISION_VERDICT_APPLIED",{"request_id":request_id,"verdict":verdict},now)
        return True

    def unresolved_supervision_request_ids(self, task_id: str | None = None) -> tuple[str,...]:
        terminal=sorted(v.value for v in TERMINAL_VERDICTS); placeholders=",".join("?" for _ in terminal)
        sql=f"SELECT request_id FROM supervision_requests WHERE (applied_verdict IS NULL OR applied_verdict NOT IN ({placeholders}))"; params=list(terminal)
        if task_id is not None: sql += " AND task_id=?"; params.append(task_id)
        sql += " ORDER BY created_at,request_id"
        return tuple(str(r["request_id"]) for r in self._conn.execute(sql,params))

    def event_count(self, task_id: str) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM events WHERE task_id=?",(task_id,)).fetchone()[0])
    def _append_event(self, task_id: str, event_type: str, payload: dict[str,object], created_at: str) -> None:
        self._conn.execute("INSERT INTO events (task_id,event_type,payload_json,created_at) VALUES (?,?,?,?)",(task_id,event_type,canonical_json(payload),created_at))
    def close(self): self._conn.close()
    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb): self.close()
