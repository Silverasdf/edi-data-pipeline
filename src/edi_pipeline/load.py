"""Load parsed files into DuckDB: clean rows into raw tables, bad files into raw.rejects."""
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from .parse import ParsedFile, parse_directory

DDL = """
CREATE SCHEMA IF NOT EXISTS raw;
CREATE TABLE IF NOT EXISTS raw.documents (
    file_name VARCHAR, partner VARCHAR, tx_type VARCHAR, control_number VARCHAR,
    doc_number VARCHAR, po_number VARCHAR, doc_date VARCHAR, total_cents BIGINT, loaded_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS raw.document_lines (
    file_name VARCHAR, tx_type VARCHAR, line_no INTEGER, qty INTEGER, unit_price DOUBLE, sku VARCHAR);
CREATE TABLE IF NOT EXISTS raw.rejects (
    file_name VARCHAR, partner VARCHAR, tx_type VARCHAR, error_code VARCHAR, detail VARCHAR, loaded_at TIMESTAMP);
"""


def load_day(db_path: Path, day_dir: Path) -> dict:
    parsed = parse_directory(day_dir)
    con = duckdb.connect(str(db_path))
    con.execute(DDL)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Idempotent: remove anything previously loaded from these files, then insert again.
    names = [p.file_name for p in parsed]
    for table in ("raw.documents", "raw.document_lines", "raw.rejects"):
        con.execute(f"DELETE FROM {table} WHERE file_name = ANY(?)", [names])

    seen = {}  # (partner, control_number) -> first file, for duplicate-interchange detection
    for p in parsed:
        key = (p.partner, p.control_number)
        if p.control_number and key in seen and seen[key] != p.file_name:
            p.errors.append(("DUPLICATE_CONTROL", f"Control {p.control_number} already used in {seen[key]}"))
        elif p.control_number:
            seen[key] = p.file_name

    # Also detect controls already loaded on earlier days
    prior = {(r[0], r[1]): r[2] for r in con.execute(
        "SELECT partner, control_number, file_name FROM raw.documents").fetchall()}
    for p in parsed:
        key = (p.partner, p.control_number)
        if key in prior and prior[key] != p.file_name and not any(e[0] == "DUPLICATE_CONTROL" for e in p.errors):
            p.errors.append(("DUPLICATE_CONTROL", f"Control {p.control_number} already loaded from {prior[key]}"))

    good = [p for p in parsed if not p.errors]
    bad = [p for p in parsed if p.errors]
    for p in good:
        con.execute("INSERT INTO raw.documents VALUES (?,?,?,?,?,?,?,?,?)",
                    [p.file_name, p.partner, p.tx_type, p.control_number, p.doc_number,
                     p.po_number, p.doc_date, p.total_cents, now])
        for line_no, qty, price, sku in p.lines:
            con.execute("INSERT INTO raw.document_lines VALUES (?,?,?,?,?,?)",
                        [p.file_name, p.tx_type, line_no, qty, price, sku])
    for p in bad:
        for code, detail in p.errors:
            con.execute("INSERT INTO raw.rejects VALUES (?,?,?,?,?,?)",
                        [p.file_name, p.partner, p.tx_type, code, detail, now])
    con.close()
    total = len(parsed)
    return {"files": total, "loaded": len(good), "rejected": len(bad),
            "reject_rate": round(len(bad) / total, 4) if total else 0.0}
