import os
from pathlib import Path
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT_DIR = Path("/opt/airflow/project")
NEWS_FILE = os.getenv("NEWS_FILE", "/opt/airflow/project/news_input/news.csv")
NEWS_MATCH_MIN_SCORE = os.getenv("NEWS_MATCH_MIN_SCORE", "0.65")
LLM_MIN_MATCH_SCORE = os.getenv("LLM_MIN_MATCH_SCORE", NEWS_MATCH_MIN_SCORE)
LLM_ASSESS_LIMIT = os.getenv("LLM_ASSESS_LIMIT", "100")

DEFAULT_ARGS = {
    "owner": "moex-coursework",
    "retries": 1,
    "retry_delay": timedelta(minutes=1),
}


with DAG(
    dag_id="moex_news_load_and_match",
    description="Load news, match news to tickers and assess news criticality with LLM",
    start_date=pendulum.datetime(2026, 1, 1, tz="Europe/Moscow"),
    schedule=None,
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["moex", "news", "dwh", "ticker-matching", "llm"],
) as dag:
    apply_migrations = BashOperator(
        task_id="apply_clickhouse_migrations",
        bash_command=f"cd {PROJECT_DIR} && python scripts/apply_migrations.py",
    )

    build_ticker_dictionary = BashOperator(
        task_id="build_ticker_dictionary",
        bash_command=f"cd {PROJECT_DIR} && python scripts/build_ticker_dictionary.py",
    )

    load_news = BashOperator(
        task_id="load_news_file",
        bash_command=(
            f"cd {PROJECT_DIR} && "
            f"test -f {NEWS_FILE} && "
            f"python scripts/load_news.py --file {NEWS_FILE} --format auto"
        ),
    )

    extract_news_tickers = BashOperator(
        task_id="extract_news_tickers",
        bash_command=(
            f"cd {PROJECT_DIR} && "
            f"python scripts/extract_news_tickers.py "
            f"--min-score {NEWS_MATCH_MIN_SCORE} --truncate"
        ),
    )

    assess_news_criticality = BashOperator(
        task_id="assess_news_criticality_llm",
        bash_command=(
            f"cd {PROJECT_DIR} && "
            f"python scripts/assess_news_llm.py "
            f"--min-score {LLM_MIN_MATCH_SCORE} "
            f"--limit {LLM_ASSESS_LIMIT}"
        ),
    )

    apply_migrations >> build_ticker_dictionary >> load_news >> extract_news_tickers >> assess_news_criticality
