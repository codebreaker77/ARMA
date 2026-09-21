"""
ARMA Phase 5 Benchmark: Autonomous Self-Healing & Strategic Remediation
Simulates 5 realistic agent thrashing and failure loops:
  1. SCENARIO_01_SYNTAX_THRASH: Repeated invalid syntax edits in core parser
  2. SCENARIO_02_ASSERTION_DEADLOCK: Circular flawed logic patches in auth validator
  3. SCENARIO_03_REGRESSION_CASCADE: Broken downstream contract in database query builder
  4. SCENARIO_04_API_CONTRACT_MISMATCH: Repeated surface edits in API endpoints without serializer fix
  5. SCENARIO_05_ASYNC_DEADLOCK: Circular race-condition locking in concurrency worker pool

Measures:
  - Loop Escape Rate (Target: 100%)
  - Surgical Rollback Fidelity (Target: 100%)
  - Non-Destructive Work Preservation (Target: 100% stashed)
  - Post-Pivot Resolution Rate (Target: 100%)
"""

import os
import sys
import shutil
import tempfile
import time
from typing import Dict, Any, List

from layer.evidence_db import EvidenceDB
from layer.decision_engine import DecisionEngine
from layer.remediator import CheckpointManager, LoopBreaker, AlternativeStrategySynthesizer
from layer.harness_hooks import ArmaHooks
from layer.cli import format_table


def get_scenarios() -> List[Dict[str, Any]]:
    return [
        {
            "id": "SC_01_SYNTAX_THRASH",
            "domain": "Compiler/Parser",
            "task": "Resolve AST parsing ambiguity for ternary expressions",
            "target_file": "core/parser.py",
            "initial_content": "def parse_expression(token_stream):\n    return {'type': 'ternary', 'valid': True}\n",
            "unrelated_file": "utils/logger.py",
            "unrelated_content": "def log_event(msg):\n    print(f'[LOG] {msg}')\n",
            "thrashing_edits": [
                "def parse_expression(token_stream):\n    return {invalid syntax here...\n",
                "def parse_expression(token_stream):\n    if True return None\n",
                "def parse_expression(token_stream):\n    raise SyntaxError('unexpected token')\n",
            ],
            "failing_errors": [
                "SyntaxError: invalid syntax",
                "SyntaxError: invalid syntax at return",
                "SyntaxError: unexpected token"
            ],
            "pivot_file": "core/lexer.py",
            "pivot_edit": "def tokenize_ternary(stream):\n    return ['?', ':']\n"
        },
        {
            "id": "SC_02_ASSERTION_DEADLOCK",
            "domain": "Authentication",
            "task": "Fix expired JWT token revocation check",
            "target_file": "auth/session_validator.py",
            "initial_content": "def validate_token(claims):\n    return claims.get('exp', 0) > 1000\n",
            "unrelated_file": "auth/crypto.py",
            "unrelated_content": "def sha256(data):\n    return 'hash'\n",
            "thrashing_edits": [
                "def validate_token(claims):\n    return claims.get('exp') is not None\n",
                "def validate_token(claims):\n    return bool(claims.get('exp'))\n",
                "def validate_token(claims):\n    return claims.get('exp') == 1000\n",
            ],
            "failing_errors": [
                "AssertionError: True != False (expired token accepted)",
                "AssertionError: True != False (missing revocation timestamp)",
                "AssertionError: False != True (valid token rejected)"
            ],
            "pivot_file": "auth/revocation_list.py",
            "pivot_edit": "def is_revoked(token_id):\n    return token_id in revoked_cache\n"
        },
        {
            "id": "SC_03_REGRESSION_CASCADE",
            "domain": "Database ORM",
            "task": "Support nested outer joins without duplicate row projection",
            "target_file": "database/query_builder.py",
            "initial_content": "def build_join(table, condition):\n    return f'LEFT OUTER JOIN {table} ON {condition}'\n",
            "unrelated_file": "database/connection.py",
            "unrelated_content": "def get_conn():\n    return 'db_conn'\n",
            "thrashing_edits": [
                "def build_join(table, condition):\n    return f'CROSS JOIN {table}'\n",
                "def build_join(table, condition):\n    return f'INNER JOIN {table} ON {condition}'\n",
                "def build_join(table, condition):\n    return f'JOIN {table}'\n",
            ],
            "failing_errors": [
                "IntegrityError: cartesian product explosion",
                "AssertionError: 0 rows returned, expected 5",
                "OperationalError: ambiguous column reference"
            ],
            "pivot_file": "database/schema_graph.py",
            "pivot_edit": "def deduplicate_projections(query):\n    return query + ' GROUP BY id'\n"
        },
        {
            "id": "SC_04_API_CONTRACT_MISMATCH",
            "domain": "REST API Gateway",
            "task": "Fix serialization of UTC ISO8601 millisecond timestamps",
            "target_file": "api/endpoints.py",
            "initial_content": "def format_response(ts):\n    return {'timestamp': str(ts)}\n",
            "unrelated_file": "api/middleware.py",
            "unrelated_content": "def cors_header():\n    return {'Access-Control-Allow-Origin': '*'}\n",
            "thrashing_edits": [
                "def format_response(ts):\n    return {'timestamp': int(ts)}\n",
                "def format_response(ts):\n    return {'timestamp': float(ts)}\n",
                "def format_response(ts):\n    return {'timestamp': ts.isoformat() if hasattr(ts, 'isoformat') else str(ts)}\n",
            ],
            "failing_errors": [
                "SchemaValidationError: expected ISO8601 string, got int",
                "SchemaValidationError: expected ISO8601 string, got float",
                "SchemaValidationError: timezone offset '+00:00' missing 'Z' suffix"
            ],
            "pivot_file": "serializers/datetime_encoder.py",
            "pivot_edit": "def encode_utc_z(dt):\n    return dt.strftime('%Y-%m-%dT%H:%M:%S.%fZ')\n"
        },
        {
            "id": "SC_05_ASYNC_DEADLOCK",
            "domain": "Concurrency Engine",
            "task": "Prevent thread starvation during burst queue drain",
            "target_file": "concurrency/worker_pool.py",
            "initial_content": "def drain_queue(q):\n    return [q.get() for _ in range(q.qsize())]\n",
            "unrelated_file": "concurrency/metrics.py",
            "unrelated_content": "def count_workers():\n    return 4\n",
            "thrashing_edits": [
                "def drain_queue(q):\n    while True: q.get()\n",
                "def drain_queue(q):\n    with lock: time.sleep(0.5); return []\n",
                "def drain_queue(q):\n    lock.acquire(); return [q.get_nowait()]\n",
            ],
            "failing_errors": [
                "TimeoutError: deadlocked waiting for sentinel",
                "ThreadStarvationException: main loop blocked",
                "DeadlockDetected: lock held without release"
            ],
            "pivot_file": "concurrency/semaphore_manager.py",
            "pivot_edit": "def acquire_with_timeout(sem, timeout=0.1):\n    return sem.acquire(timeout=timeout)\n"
        }
    ]


def run_benchmark():
    print("=" * 85)
    print("ARMA PHASE 5 BENCHMARK: AUTONOMOUS SELF-HEALING & STRATEGIC REMEDIATION")
    print("Evaluating LoopBreaker, Surgical Rollback Fidelity & Strategic Pivots")
    print("=" * 85)

    scenarios = get_scenarios()
    results = []

    total_scenarios = len(scenarios)
    loops_broken = 0
    rollbacks_verified = 0
    stashes_preserved = 0
    pivots_synthesized = 0
    resolved_post_pivot = 0

    for sc in scenarios:
        temp_dir = tempfile.mkdtemp(prefix=f"arma_bench_{sc['id']}_")
        storage_dir = tempfile.mkdtemp(prefix="arma_bench_ckpts_")
        db_path = os.path.join(temp_dir, "bench_evidence.db")

        try:
            # 1. Setup simulated repository files
            target_path = os.path.join(temp_dir, sc["target_file"])
            unrelated_path = os.path.join(temp_dir, sc["unrelated_file"])
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            os.makedirs(os.path.dirname(unrelated_path), exist_ok=True)

            with open(target_path, "w", encoding="utf-8") as f:
                f.write(sc["initial_content"])
            with open(unrelated_path, "w", encoding="utf-8") as f:
                f.write(sc["unrelated_content"])

            # 2. Initialize ARMA Layer with CheckpointManager & LoopBreaker
            db = EvidenceDB(db_path=db_path)
            ckpt_mgr = CheckpointManager(storage_dir=storage_dir)
            engine = DecisionEngine(evidence_db=db, default_mode="enforce")
            hooks = ArmaHooks(db=db, engine=engine, checkpoint_mgr=ckpt_mgr)

            session_id = hooks.on_session_start(
                repo_path=temp_dir,
                harness="benchmark_harness",
                task_text=sc["task"],
                checklist=[sc["task"]]
            )

            # Turn 1: Passing baseline test -> records clean green checkpoint
            hooks.on_tool_output(
                session_id=session_id,
                tool_name="pytest",
                raw_output="test_baseline.py . [100%]\n1 passed in 0.02s",
                exit_code=0
            )

            # Turns 2 & 3: Agent makes flawed edits, tests fail
            for i in range(2):
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(sc["thrashing_edits"][i])

                hooks.on_tool_output(
                    session_id=session_id,
                    tool_name="pytest",
                    raw_output=f"FAILED {sc['target_file']}: {sc['failing_errors'][i]}",
                    exit_code=1
                )

                gate_res = hooks.on_pre_tool_use(
                    session_id=session_id,
                    tool_name="replace_file_content",
                    tool_args={"TargetFile": sc["target_file"]}
                )
                # First two edits are allowed through
                assert gate_res.allow is True

            # Turn 4: Agent attempts 3rd thrashing edit on same file while failing
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(sc["thrashing_edits"][2])

            hooks.on_tool_output(
                session_id=session_id,
                tool_name="pytest",
                raw_output=f"FAILED {sc['target_file']}: {sc['failing_errors'][2]}",
                exit_code=1
            )

            # ARMA Interception Gate
            intervention_result = hooks.on_pre_tool_use(
                session_id=session_id,
                tool_name="replace_file_content",
                tool_args={"TargetFile": sc["target_file"]}
            )

            # Verify Loop Breaker triggered intervention
            is_loop_broken = (
                intervention_result.module == "loop_detector"
                and intervention_result.counterfactual_action == "rollback"
                and intervention_result.action_taken in ("intervene", "remediate")
                and intervention_result.allow is False  # Enforce mode blocks repeat thrash
            )
            if is_loop_broken:
                loops_broken += 1

            # Verify Surgical Rollback restored initial clean content
            with open(target_path, "r", encoding="utf-8") as f:
                restored_content = f.read()
            is_restored = (restored_content == sc["initial_content"])
            if is_restored:
                rollbacks_verified += 1

            # Verify unrelated files remained intact (surgical precision)
            with open(unrelated_path, "r", encoding="utf-8") as f:
                unrelated_now = f.read()
            is_unrelated_intact = (unrelated_now == sc["unrelated_content"])

            # Verify safety stash was preserved
            stash_files = os.listdir(ckpt_mgr.stash_dir)
            is_stashed = len(stash_files) > 0
            if is_stashed:
                stashes_preserved += 1

            # Verify Strategic Pivot directive was generated and injected into context tail
            sess_obj = hooks.active_sessions[session_id]
            pinned_context = sess_obj["pinned_facts"].format_pinned_facts()
            is_pivot_injected = (
                "CRITICAL INTERVENTION: EDIT-FAIL LOOP DETECTED" in pinned_context
                and sc["target_file"] in pinned_context
                and "STRATEGIC PIVOT DIRECTIVE" in pinned_context
            )
            if is_pivot_injected:
                pivots_synthesized += 1

            # Simulate Agent following the pivot guidance:
            # Agent ceases edits on target_file and implements fix in pivot_file
            pivot_path = os.path.join(temp_dir, sc["pivot_file"])
            os.makedirs(os.path.dirname(pivot_path), exist_ok=True)
            with open(pivot_path, "w", encoding="utf-8") as f:
                f.write(sc["pivot_edit"])

            # Pivot test succeeds!
            hooks.on_tool_output(
                session_id=session_id,
                tool_name="pytest",
                raw_output=f"test_pivot.py . [100%]\nAll tests passed after strategic pivot to {sc['pivot_file']}",
                exit_code=0
            )

            # Agent requests stop
            stop_res = hooks.on_stop_requested(
                session_id=session_id,
                test_results={"exit_code": 0, "passed": True},
                diff_stat=f"1 file changed, 2 insertions(+) in {sc['pivot_file']}"
            )
            is_resolved = stop_res.allow is True
            if is_resolved:
                resolved_post_pivot += 1

            results.append([
                sc["id"],
                sc["domain"],
                "BROKEN" if is_loop_broken else "MISSED",
                "100% RESTORED" if (is_restored and is_unrelated_intact) else "CORRUPTED",
                "PRESERVED" if is_stashed else "LOST",
                "INJECTED" if is_pivot_injected else "NONE",
                "RESOLVED (0)" if is_resolved else "FAILED"
            ])

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            shutil.rmtree(storage_dir, ignore_errors=True)

    headers = [
        "Scenario ID",
        "Domain",
        "Loop Breaker",
        "Surgical Rollback",
        "Recovery Stash",
        "Pivot Directive",
        "Post-Pivot Status"
    ]
    print(format_table(headers, results))

    escape_rate = (loops_broken / total_scenarios) * 100.0
    rollback_fidelity = (rollbacks_verified / total_scenarios) * 100.0
    stash_retention = (stashes_preserved / total_scenarios) * 100.0
    pivot_rate = (pivots_synthesized / total_scenarios) * 100.0
    resolution_rate = (resolved_post_pivot / total_scenarios) * 100.0

    print("\n" + "=" * 85)
    print("ARMA PHASE 5 SELF-HEALING & REMEDIATION BENCHMARK SUMMARY")
    print("=" * 85)
    print(f"Total Scenarios Evaluated       : {total_scenarios}")
    print(f"Loop Escape Rate (Intervention) : {escape_rate:.1f}% (Target: 100.0%)")
    print(f"Surgical Rollback Fidelity      : {rollback_fidelity:.1f}% (Target: 100.0%)")
    print(f"Non-Destructive Stash Safety    : {stash_retention:.1f}% (Target: 100.0%)")
    print(f"Strategic Pivot Context Injection: {pivot_rate:.1f}% (Target: 100.0%)")
    print(f"Post-Pivot Task Resolution Rate : {resolution_rate:.1f}% (Target: 100.0%)")
    print("=" * 85)

    assert escape_rate == 100.0, f"Loop escape rate {escape_rate}% did not meet 100% target"
    assert rollback_fidelity == 100.0, f"Rollback fidelity {rollback_fidelity}% did not meet 100% target"
    assert stash_retention == 100.0, f"Stash safety {stash_retention}% did not meet 100% target"
    assert pivot_rate == 100.0, f"Strategic pivot rate {pivot_rate}% did not meet 100% target"
    assert resolution_rate == 100.0, f"Resolution rate {resolution_rate}% did not meet 100% target"

    print("\n[SUCCESS] All Phase 5 self-healing, rollback, and strategic pivot targets achieved!")


if __name__ == "__main__":
    run_benchmark()
