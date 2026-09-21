"""
ARMA Developer CLI & Telemetry Dashboard
Provides command-line utilities to inspect agent sessions, review counterfactual decisions,
and monitor model calibration.
"""

import sys
import argparse
from layer.evidence_db import EvidenceDB


def format_table(headers, rows):
    """Simple Markdown/plain table formatter."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))

    header_line = "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"
    sep_line = "|-" + "-|-".join("-" * col_widths[i] for i in range(len(headers))) + "-|"
    data_lines = [
        "| " + " | ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row)) + " |"
        for row in rows
    ]
    return "\n".join([header_line, sep_line] + data_lines)


def cmd_status(args):
    """Display overall system status and module promotion states."""
    db = EvidenceDB()
    with db._get_connection() as conn:
        sessions_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        events_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        decisions_count = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        outcomes_count = conn.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]

    print("=" * 65)
    print("ARMA System Status")
    print("=" * 65)
    print(f"Database Path    : {db.db_path}")
    print(f"Total Sessions   : {sessions_count}")
    print(f"Total Events     : {events_count}")
    print(f"Total Decisions  : {decisions_count}")
    print(f"Labeled Outcomes : {outcomes_count}")
    print("-" * 65)
    print("Module Promotion States:")
    print("  Stop Gate     : shadow (Logs counterfactuals)")
    print("  Scope Gate    : shadow (Logs counterfactuals)")
    print("  Risk Gate     : shadow (Hard deny active in code)")
    print("  Loop Detector : shadow (Logs counterfactuals)")
    print("=" * 65)


def cmd_tail(args):
    """Display recent decisions and counterfactuals."""
    db = EvidenceDB()
    decisions = db.get_recent_decisions(limit=args.limit)

    if not decisions:
        print("No decisions recorded yet.")
        return

    print("=" * 75)
    print(f"Recent ARMA Decisions (Last {len(decisions)})")
    print("=" * 75)

    headers = ["Module", "Turn", "Kind", "Mode", "Action", "Counterfactual", "Confidence"]
    rows = []
    for d in decisions:
        rows.append([
            d["module"],
            d["turn"],
            d["kind"],
            d["mode"],
            d["action_taken"],
            d["counterfactual_action"] or "n/a",
            f"{d['confidence']:.2f}"
        ])
    print(format_table(headers, rows))


def cmd_calibrate(args):
    """Compute and display calibration metrics and Expected Calibration Error."""
    db = EvidenceDB()
    metrics = db.calculate_calibration_metrics(module=args.module)

    print("=" * 65)
    print(f"ARMA Calibration Report {'(' + args.module + ')' if args.module else '(All Modules)'}")
    print("=" * 65)
    print(f"Total Labeled Decisions : {metrics['total_labeled']}")
    print(f"Measured Precision      : {metrics['precision']:.4f}")
    print(f"Measured Recall         : {metrics['recall']:.4f}")
    print(f"Expected Calibration Err: {metrics['ece']:.4f}")
    print(f"Promotion Status        : {metrics['status']}")
    print("=" * 65)


def cmd_replay(args):
    """Replay historical traces through candidate calibration policies."""
    from layer.replay_engine import ReplayEngine
    from layer.calibrator import CalibrationStore

    engine = ReplayEngine()
    config = CalibrationStore.load()

    if args.session:
        summary = engine.replay_session(session_id=args.session, candidate_config=config)
    else:
        summary = engine.replay_all(module=args.module, candidate_config=config)

    print("=" * 75)
    print("ARMA Counterfactual Trace Replay Summary")
    print("=" * 75)
    print(f"Total Decisions Replayed      : {summary.total_replayed}")
    print(f"Original Baseline Accuracy    : {summary.original_accuracy * 100:.2f}%")
    print(f"Candidate Calibrated Accuracy : {summary.candidate_accuracy * 100:.2f}%")
    print(f"Counterfactual Net Lift       : {summary.counterfactual_lift * 100:+.2f}%")
    print(f"Baseline False Stops          : {summary.original_false_stops}")
    print(f"Candidate False Stops         : {summary.candidate_false_stops}")
    print(f"Net False Alarms Eliminated   : {summary.net_false_alarms_eliminated}")
    print("-" * 75)
    if summary.diffs:
        print(f"Decision Flips ({len(summary.diffs)} total):")
        for d in summary.diffs[:5]:
            print(f"  [{d.module}] Turn {d.turn}: {d.original_action} -> {d.candidate_action} (Truth: {d.ground_truth})")
    print("=" * 75)


def cmd_optimize(args):
    """Run temperature scaling and decision threshold optimization on EvidenceDB."""
    from layer.calibrator import OfflineCalibrator

    calibrator = OfflineCalibrator()
    if args.module:
        res = {args.module: calibrator.optimize_module(args.module)}
    else:
        res = calibrator.optimize_all_modules(save=True)

    print("=" * 80)
    print("ARMA Continuous Probability Calibration & Threshold Optimization")
    print("=" * 80)

    headers = ["Module", "Samples", "Opt Temp", "Opt Tau", "Init ECE", "Cal ECE", "F1 Score", "Status"]
    rows = []
    for mod, r in res.items():
        rows.append([
            mod,
            str(r.get("samples", 0)),
            f"{r.get('temperature', 1.0):.2f}",
            f"{r.get('threshold', 0.5):.2f}",
            f"{r.get('initial_ece', 0.0):.4f}",
            f"{r.get('calibrated_ece', 0.0):.4f}",
            f"{r.get('f1_score', 0.0):.4f}",
            r.get("status", "UNKNOWN")
        ])
    print(format_table(headers, rows))
    print("=" * 80)
    print("Calibration parameters saved to arma_calibration.json")


def cmd_export(args):
    """Export labeled Evidence Plane traces into ML distillation datasets."""
    from layer.distill_exporter import DistillExporter

    exporter = DistillExporter()
    output_path = args.output

    if args.format == "triplets":
        count = exporter.export_contrastive_triplets(
            output_path=output_path,
            module=args.module,
            only_disagreements=args.disagreements_only
        )
    else:
        count = exporter.export_instruction_tuning(
            output_path=output_path,
            format_type=args.format,
            module=args.module
        )

    print("=" * 70)
    print("ARMA Distillation Dataset Export")
    print("=" * 70)
    print(f"Export Format      : {args.format}")
    print(f"Records Exported   : {count}")
    print(f"Destination File   : {output_path}")
    print("=" * 70)


def cmd_run(args):
    """Execute a coding harness with automatic ARMA proxy intercept and telemetry."""
    from layer.runner import HarnessRunner
    if not args.cmd:
        print("Error: No harness command specified. Example: arma run claude")
        sys.exit(1)
    runner = HarnessRunner(port=args.port)
    exit_code = runner.run(command=args.cmd)
    sys.exit(exit_code)


def cmd_mcp(args):
    """Start native Model Context Protocol (MCP) stdio server."""
    from layer.mcp_server import run_mcp_server
    run_mcp_server()


def cmd_dashboard(args):
    """Launch the ARMA Real-Time Web Telemetry Dashboard."""
    from layer.web_dashboard import run_dashboard
    run_dashboard(port=args.port)


def main():
    parser = argparse.ArgumentParser(prog="arma", description="ARMA Layer CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # status
    p_status = subparsers.add_parser("status", help="Show system status and recorded totals")
    p_status.set_defaults(func=cmd_status)

    # tail
    p_tail = subparsers.add_parser("tail", help="Display recent decisions and counterfactuals")
    p_tail.add_argument("-n", "--limit", type=int, default=15, help="Number of records to show")
    p_tail.set_defaults(func=cmd_tail)

    # calibrate
    p_cal = subparsers.add_parser("calibrate", help="Calculate precision, recall, and ECE")
    p_cal.add_argument("-m", "--module", type=str, default=None, help="Specific module to calibrate")
    p_cal.set_defaults(func=cmd_calibrate)

    # replay
    p_replay = subparsers.add_parser("replay", help="Replay traces through candidate policies")
    p_replay.add_argument("-s", "--session", type=str, default=None, help="Specific session ID to replay")
    p_replay.add_argument("-m", "--module", type=str, default=None, help="Filter by specific module")
    p_replay.set_defaults(func=cmd_replay)

    # optimize
    p_opt = subparsers.add_parser("optimize", help="Fit temperature scaling and decision thresholds")
    p_opt.add_argument("-m", "--module", type=str, default=None, help="Specific module to optimize")
    p_opt.set_defaults(func=cmd_optimize)

    # export
    p_exp = subparsers.add_parser("export", help="Export labeled traces into training datasets")
    p_exp.add_argument("-f", "--format", choices=["triplets", "alpaca", "sharegpt"], default="triplets", help="Output format")
    p_exp.add_argument("-o", "--output", type=str, default="data/arma_distill.jsonl", help="Target output file path")
    p_exp.add_argument("-m", "--module", type=str, default=None, help="Filter by specific module")
    p_exp.add_argument("--disagreements-only", action="store_true", help="Only export high-leverage disagreement samples")
    p_exp.set_defaults(func=cmd_export)

    # run
    p_run = subparsers.add_parser("run", help="Launch an agent harness with ARMA interception")
    p_run.add_argument("-p", "--port", type=int, default=4040, help="Proxy port (default 4040)")
    p_run.add_argument("cmd", nargs=argparse.REMAINDER, help="Harness command to run (e.g. claude, aider)")
    p_run.set_defaults(func=cmd_run)

    # mcp
    p_mcp = subparsers.add_parser("mcp", help="Start native Model Context Protocol (MCP) stdio server")
    p_mcp.set_defaults(func=cmd_mcp)

    # dashboard
    p_dash = subparsers.add_parser("dashboard", help="Start Real-Time Web Telemetry Dashboard")
    p_dash.add_argument("-p", "--port", type=int, default=4041, help="Dashboard port (default 4041)")
    p_dash.set_defaults(func=cmd_dashboard)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
