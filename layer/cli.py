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

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
