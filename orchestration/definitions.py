"""Dagster definitions: generate -> load -> dbt build, on a daily schedule with retries."""
import subprocess
from datetime import date
from pathlib import Path

from dagster import (Definitions, Failure, MaterializeResult, MetadataValue, RetryPolicy,
                     ScheduleDefinition, asset, define_asset_job)

from edi_pipeline.generate import generate
from edi_pipeline.load import load_day

ROOT = Path(__file__).resolve().parent.parent
LANDING = ROOT / "data" / "landing"
DB_PATH = ROOT / "data" / "warehouse.duckdb"
MAX_REJECT_RATE = 0.30  # fail the run if more than 30% of files are rejected


@asset(retry_policy=RetryPolicy(max_retries=2, delay=10))
def landed_files() -> MaterializeResult:
    """Pretend partners dropped today's files into the landing folder."""
    day_dir, manifest = generate(LANDING, date.today())
    return MaterializeResult(metadata={"folder": str(day_dir), "files": len(manifest)})


@asset(deps=[landed_files], retry_policy=RetryPolicy(max_retries=2, delay=10))
def raw_tables() -> MaterializeResult:
    """Parse, validate, and load into DuckDB. Fails loudly if too many files are rejected."""
    stats = load_day(DB_PATH, LANDING / date.today().isoformat())
    if stats["reject_rate"] > MAX_REJECT_RATE:
        raise Failure(description=f"Reject rate {stats['reject_rate']:.0%} is above {MAX_REJECT_RATE:.0%}",
                      metadata={k: v for k, v in stats.items()})
    return MaterializeResult(metadata={k: MetadataValue.float(float(v)) for k, v in stats.items()})


@asset(deps=[raw_tables])
def warehouse_models() -> MaterializeResult:
    """Run dbt models and tests. A failing test fails the asset."""
    result = subprocess.run(["dbt", "build", "--profiles-dir", "."], cwd=ROOT / "dbt_project",
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise Failure(description="dbt build failed", metadata={"output": MetadataValue.text(result.stdout[-3000:])})
    return MaterializeResult(metadata={"dbt_summary": MetadataValue.text(result.stdout.strip().splitlines()[-1])})


daily_job = define_asset_job("daily_edi_load", selection="*")
daily_schedule = ScheduleDefinition(job=daily_job, cron_schedule="0 6 * * *")

defs = Definitions(assets=[landed_files, raw_tables, warehouse_models],
                   jobs=[daily_job], schedules=[daily_schedule])
