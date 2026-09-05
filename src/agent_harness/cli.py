from __future__ import annotations
import argparse, shlex
from pathlib import Path
from .domain import ScopeBudget, TaskIntent, TaskStatement
from .orchestrator import Slice0Orchestrator
from .provider import FixedCommandProvider
from .store import HarnessStore


def build_parser() -> argparse.ArgumentParser:
    parser=argparse.ArgumentParser(prog="fil-harness")
    run=parser.add_subparsers(dest="command",required=True).add_parser("run",help="Run one governed task")
    run.add_argument("--repo",required=True); run.add_argument("--intent",required=True,choices=[i.value for i in TaskIntent]); run.add_argument("--desired-behavior",required=True); run.add_argument("--current-behavior")
    run.add_argument("--provider-command",required=True); run.add_argument("--acceptance",action="append",default=[]); run.add_argument("--constraint",action="append",default=[]); run.add_argument("--allow-path",action="append",default=[]); run.add_argument("--max-files",type=int); run.add_argument("--max-loc",type=int)
    run.add_argument("--provider-timeout",type=float,default=900.0); run.add_argument("--verification-timeout",type=float,default=300.0); run.add_argument("--runtime-root",default=str(Path.home()/".fil-harness")); run.add_argument("--verification-justification")
    return parser

def main(argv: list[str] | None = None) -> int:
    args=build_parser().parse_args(argv)
    if args.command != "run": return 2
    try: statement=TaskStatement(intent=TaskIntent(args.intent),desired_behavior=args.desired_behavior,current_behavior=args.current_behavior)
    except ValueError as exc: print(f"invalid task statement: {exc}"); return 2
    runtime_root=Path(args.runtime_root).expanduser().resolve(); store=HarnessStore(runtime_root/"harness.db")
    try:
        result=Slice0Orchestrator(store=store,provider=FixedCommandProvider(tuple(shlex.split(args.provider_command))),runtime_root=runtime_root,provider_timeout_s=args.provider_timeout,verification_timeout_s=args.verification_timeout).run(repo_path=args.repo,statement=statement,acceptance=tuple(args.acceptance),constraints=tuple(args.constraint),scope=ScopeBudget(tuple(args.allow_path),args.max_files,args.max_loc),verification_justification=args.verification_justification)
        print(result.summary); return 0 if result.ready else 2
    finally: store.close()

if __name__ == "__main__": raise SystemExit(main())
