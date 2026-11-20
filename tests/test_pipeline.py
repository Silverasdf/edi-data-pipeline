from datetime import date
from pathlib import Path

import duckdb

from edi_pipeline.generate import generate
from edi_pipeline.load import load_day
from edi_pipeline.parse import parse_directory, parse_file


def test_clean_files_have_no_errors(tmp_path):
    day_dir, _ = generate(tmp_path, date(2026, 1, 5), n_pairs=10, error_rate=0.0)
    assert all(not p.errors for p in parse_directory(day_dir))


def test_every_injected_error_is_caught_and_nothing_else(tmp_path):
    day_dir, manifest = generate(tmp_path, date(2026, 1, 6), n_pairs=60, error_rate=0.2)
    injected = {m["file"] for m in manifest if m["injected_error"]}
    rejected = {p.file_name for p in parse_directory(day_dir) if p.errors}
    # Duplicate-control detection needs the loader's cross-file memory, so compare via a full load.
    stats = load_day(tmp_path / "wh.duckdb", day_dir)
    con = duckdb.connect(str(tmp_path / "wh.duckdb"))
    rejected = {r[0] for r in con.execute("select distinct file_name from raw.rejects").fetchall()}
    assert rejected == injected
    assert stats["rejected"] == len(injected)


def test_loading_twice_does_not_duplicate_rows(tmp_path):
    day_dir, _ = generate(tmp_path, date(2026, 1, 7), n_pairs=20, error_rate=0.1)
    db = tmp_path / "wh.duckdb"
    load_day(db, day_dir)
    first = duckdb.connect(str(db)).execute("select count(*) from raw.documents").fetchone()[0]
    load_day(db, day_dir)
    second = duckdb.connect(str(db)).execute("select count(*) from raw.documents").fetchone()[0]
    assert first == second


def test_spoofed_sender_is_rejected(tmp_path):
    day_dir, _ = generate(tmp_path, date(2026, 2, 1), n_pairs=4, error_rate=0.0)
    path = sorted(day_dir.glob("*.edi"))[0]
    known = parse_file(path).partner
    path.write_text(path.read_text().replace(known.ljust(15), "EVILVENDOR".ljust(15), 1))
    codes = [code for code, _ in parse_file(path).errors]
    assert "UNKNOWN_SENDER" in codes


def test_outlier_invoices_still_parse_cleanly(tmp_path):
    day_dir, manifest = generate(tmp_path, date(2026, 2, 2), n_pairs=100, error_rate=1.0)
    parsed = {p.file_name: p for p in parse_directory(day_dir)}
    outliers = [m for m in manifest if m["injected_anomaly"] == "outlier_amount"]
    assert outliers
    assert all(not parsed[m["file"]].errors for m in outliers)
