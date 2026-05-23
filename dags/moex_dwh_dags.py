import os
from pathlib import Path

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator


PROJECT_DIR = Path("/opt/airflow/project")
SAMPLES_DIR = PROJECT_DIR / "samples"
TMP_DIR = Path("/tmp/algopack")

DEFAULT_ARGS = {
    "owner": "moex-coursework",
    "retries": 1,
}


def csv_env(name: str, default: str) -> list[str]:
    value = os.getenv(name, default)
    return [item.strip().upper() for item in value.split(",") if item.strip()]


TICKERS = csv_env("MOEX_TICKERS", "SBER")
ALGOPACK_KINDS = [
    kind.strip().lower()
    for kind in os.getenv("ALGOPACK_KINDS", "obstats,orderstats,tradestats").split(",")
    if kind.strip()
]

with DAG(
    dag_id="moex_dwh_load_samples",
    description="Load local sample JSON files into ClickHouse DWH",
    start_date=pendulum.datetime(2026, 1, 1, tz="Europe/Moscow"),
    schedule=None,
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["moex", "dwh", "samples", "clickhouse"],
) as sample_dag:
    apply_migrations = BashOperator(
        task_id="apply_clickhouse_migrations",
        bash_command=f"cd {PROJECT_DIR} && python scripts/apply_migrations.py",
    )

    load_obstats = BashOperator(
        task_id="load_sample_obstats",
        bash_command=f"cd {PROJECT_DIR} && python scripts/load_json.py --kind obstats --file {SAMPLES_DIR}/obstats.json --ticker SBER --date 2026-05-22",
    )

    load_orderstats = BashOperator(
        task_id="load_sample_orderstats",
        bash_command=f"cd {PROJECT_DIR} && python scripts/load_json.py --kind orderstats --file {SAMPLES_DIR}/orderstats.json --ticker SBER --date 2026-05-22",
    )

    load_tradestats = BashOperator(
        task_id="load_sample_tradestats",
        bash_command=f"cd {PROJECT_DIR} && python scripts/load_json.py --kind tradestats --file {SAMPLES_DIR}/tradestats.json --ticker SBER --date 2026-05-22",
    )

    load_orderbook = BashOperator(
        task_id="load_sample_orderbook",
        bash_command=f"cd {PROJECT_DIR} && python scripts/load_json.py --kind orderbook --file {SAMPLES_DIR}/orderbook.json --ticker SBER --date 2026-05-22",
    )

    load_securities = BashOperator(
        task_id="load_sample_securities",
        bash_command=f"cd {PROJECT_DIR} && python scripts/load_json.py --kind securities --file {SAMPLES_DIR}/securities.json --ticker ALL --date 2026-05-22",
    )

    apply_migrations >> [load_securities, load_obstats, load_orderstats, load_tradestats, load_orderbook]


with DAG(
    dag_id="moex_dwh_algopack_daily",
    description="Fetch MOEX AlgoPack 5-minute metrics and load them into ClickHouse DWH",
    start_date=pendulum.datetime(2026, 1, 1, tz="Europe/Moscow"),
    schedule="0 23 * * 1-5",
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["moex", "algopack", "dwh", "clickhouse"],
) as algopack_dag:
    apply_migrations = BashOperator(
        task_id="apply_clickhouse_migrations",
        bash_command=f"cd {PROJECT_DIR} && python scripts/apply_migrations.py",
    )

    # Refresh instruments once per run. This is a dimension-like source.
    fetch_securities = BashOperator(
        task_id="fetch_securities",
        bash_command=(
            f"cd {PROJECT_DIR} && "
            f"python scripts/fetch_algopack.py --kind securities --ticker ALL --date {{{{ ds }}}} "
            f"--output {TMP_DIR}/{{{{ ds }}}}/securities.json"
        ),
    )

    load_securities = BashOperator(
        task_id="load_securities",
        bash_command=(
            f"cd {PROJECT_DIR} && "
            f"python scripts/load_json.py --kind securities --file {TMP_DIR}/{{{{ ds }}}}/securities.json "
            f"--ticker ALL --date {{{{ ds }}}} --endpoint securities"
        ),
    )

    apply_migrations >> fetch_securities >> load_securities

    for ticker in TICKERS:
        previous_task = load_securities
        for kind in ALGOPACK_KINDS:
            fetch_task = BashOperator(
                task_id=f"fetch_{kind}_{ticker}",
                bash_command=(
                    f"cd {PROJECT_DIR} && "
                    f"python scripts/fetch_algopack.py --kind {kind} --ticker {ticker} --date {{{{ ds }}}} "
                    f"--output {TMP_DIR}/{{{{ ds }}}}/{kind}_{ticker}.json"
                ),
            )

            load_task = BashOperator(
                task_id=f"load_{kind}_{ticker}",
                bash_command=(
                    f"cd {PROJECT_DIR} && "
                    f"python scripts/load_json.py --kind {kind} --file {TMP_DIR}/{{{{ ds }}}}/{kind}_{ticker}.json "
                    f"--ticker {ticker} --date {{{{ ds }}}} --endpoint {kind}/{ticker}"
                ),
            )

            previous_task >> fetch_task >> load_task
            previous_task = load_task
