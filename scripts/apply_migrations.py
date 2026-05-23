import hashlib
import os
import time
from pathlib import Path

import clickhouse_connect
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"


def get_client():
    load_dotenv(PROJECT_ROOT / ".env")
    return clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST", "localhost"),
        port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        username=os.getenv("CLICKHOUSE_USER", "default"),
        password=os.getenv("CLICKHOUSE_PASSWORD", ""),
        secure=os.getenv("CLICKHOUSE_SECURE", "false").lower() == "true",
    )


def split_sql(sql: str) -> list[str]:
    statements = []
    current = []
    in_single_quote = False

    for char in sql:
        if char == "'":
            in_single_quote = not in_single_quote
        if char == ";" and not in_single_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)

    return statements


def ensure_migration_table(client):
    client.command("CREATE DATABASE IF NOT EXISTS meta")
    client.command("""
        CREATE TABLE IF NOT EXISTS meta.schema_migrations
        (
            version String,
            filename String,
            checksum String,
            applied_at DateTime DEFAULT now(),
            execution_ms UInt64
        )
        ENGINE = MergeTree
        ORDER BY version
    """)


def applied_versions(client) -> set[str]:
    result = client.query("SELECT version FROM meta.schema_migrations")
    return {row[0] for row in result.result_rows}


def main():
    client = get_client()
    ensure_migration_table(client)

    applied = applied_versions(client)
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))

    for path in files:
        version = path.name.split("_", 1)[0]
        if version in applied:
            print(f"SKIP {path.name}")
            continue

        sql = path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        statements = split_sql(sql)

        print(f"APPLY {path.name} ({len(statements)} statements)")
        started = time.time()

        for statement in statements:
            client.command(statement)

        elapsed_ms = int((time.time() - started) * 1000)
        client.insert(
            "meta.schema_migrations",
            [(version, path.name, checksum, elapsed_ms)],
            column_names=["version", "filename", "checksum", "execution_ms"],
        )
        print(f"DONE {path.name} in {elapsed_ms} ms")


if __name__ == "__main__":
    main()
