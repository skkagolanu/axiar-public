"""Run backend regression tests in a separate disposable database, outside load runs."""

import asyncio
import subprocess
import sys
from pathlib import Path

import asyncpg
from environment import DB_URL, REDIS_URL, environment

ROOT = Path(__file__).resolve().parents[1]
TEST_URL = DB_URL.replace("/axiar_benchmark", "/axiar_benchmark_test")


async def prepare():
    conn = await asyncpg.connect(DB_URL.replace("postgresql+asyncpg", "postgresql"))
    assert await conn.fetchval("SELECT current_database()") == "axiar_benchmark"
    if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname='axiar_benchmark_test'"):
        await conn.execute("CREATE DATABASE axiar_benchmark_test")
    await conn.close()
    conn = await asyncpg.connect(TEST_URL.replace("postgresql+asyncpg", "postgresql"))
    assert await conn.fetchval("SELECT current_database()") == "axiar_benchmark_test"
    await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public; CREATE EXTENSION postgis")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(prepare())
    env = environment()
    env.update(
        DATABASE_URL=TEST_URL,
        TEST_DATABASE_URL=TEST_URL,
        REDIS_URL=REDIS_URL.replace("/0", "/1"),
        KAFKA_BOOTSTRAP_SERVERS="",
        ALLOWED_HOSTS="*",
        PYTHONPATH=str(ROOT / "backend"),
    )
    # Repository queries use the real migration's immutable range function/index;
    # metadata-only table creation cannot validate that database contract.
    subprocess.run([str(ROOT / "backend/.venv/bin/python"), "-m", "alembic", "upgrade", "head"],
                   cwd=ROOT / "backend", env=env, check=True, stdout=subprocess.DEVNULL)
    with (ROOT / "benchmarks/results/pytest.log").open("w") as log:
        result = subprocess.run(
            [str(ROOT / "backend/.venv/bin/python"), "-m", "pytest", "--tb=short", *sys.argv[1:]],
            cwd=ROOT / "backend",
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    print("pytest exit:", result.returncode)
    raise SystemExit(result.returncode)
