"""Score the synthetic security checks against the generator's manifest."""
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import duckdb

from .generate import generate
from .load import load_day

ROOT = Path(__file__).resolve().parents[2]
DBT_PROJECT = ROOT / "dbt_project"
DEFAULT_DATE = date(2026, 11, 19)


def evaluate(out_dir: Path, db_path: Path, run_date: date, n_pairs: int = 300) -> dict:
    """Generate a seeded batch, load it, run dbt, then compare findings to the manifest."""
    day_dir, manifest = generate(out_dir, run_date, n_pairs=n_pairs, error_rate=0.15)
    load_day(db_path, day_dir)

    env = os.environ.copy()
    env["DBT_DUCKDB_PATH"] = str(db_path.resolve())
    result = subprocess.run(
        ["dbt", "build", "--profiles-dir", ".", "--target", "security"],
        cwd=DBT_PROJECT, env=env, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"dbt build failed:\n{result.stdout[-3000:]}\n{result.stderr[-3000:]}")

    con = duckdb.connect(str(db_path))
    spoofed_files = {m["file"] for m in manifest if m["injected_error"] == "spoofed_sender"}
    unknown_sender_files = {r[0] for r in con.execute(
        "select distinct file_name from raw.rejects where error_code = 'UNKNOWN_SENDER'").fetchall()}
    outlier_invoices = {m["doc_number"] for m in manifest
                        if m["injected_anomaly"] == "outlier_amount"}
    flagged_invoices = {r[0] for r in con.execute(
        "select invoice_number from main.fct_unusual_invoices").fetchall()}
    clean_invoices = {r[0] for r in con.execute(
        "select doc_number from raw.documents where tx_type = '810'").fetchall()}
    con.close()

    return {
        "files_generated": len(manifest),
        "spoofed_senders_injected": len(spoofed_files),
        "spoofed_senders_caught": len(spoofed_files & unknown_sender_files),
        "unknown_sender_false_positives": len(unknown_sender_files - spoofed_files),
        "outlier_invoices_injected": len(outlier_invoices),
        "outlier_invoices_flagged": len(outlier_invoices & flagged_invoices),
        "outlier_false_positives": len((flagged_invoices & clean_invoices) - outlier_invoices),
    }


if __name__ == "__main__":
    run_date = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATE
    base = ROOT / "data" / "security_eval"
    print(json.dumps(evaluate(base / "landing", base / "warehouse.duckdb", run_date), indent=2))
