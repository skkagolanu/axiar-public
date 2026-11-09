"""Fixed, loopback-only infrastructure; never reads deployment credentials."""

import argparse
import os
import subprocess

DB_URL = "postgresql+asyncpg://axiar:benchmark-only@127.0.0.1:55439/axiar_benchmark"
REDIS_URL = "redis://127.0.0.1:56389/0"
BROKER = "127.0.0.1:59092"
API_URL = "http://127.0.0.1:58089"
NAMES = ("axiar-bench-postgres", "axiar-bench-redis", "axiar-bench-kafka")


def docker(*args, **kwargs):
    # Set BENCH_DOCKER_PREFIX='' when the caller already has Docker access.
    prefix = os.environ.get("BENCH_DOCKER_PREFIX", "sudo -n").split()
    return subprocess.run([*prefix, "docker", *args], check=True, **kwargs)


def environment():
    env = dict(os.environ)
    # Do not inherit real integration credentials from a developer's shell.
    env.update(
        DATABASE_URL=DB_URL,
        TEST_DATABASE_URL=DB_URL,
        REDIS_URL=REDIS_URL,
        KAFKA_BOOTSTRAP_SERVERS=BROKER,
        SECRET_KEY="benchmark-only-secret-at-least-32-characters",
        SESSION_SECRET_KEY="benchmark-only-session-at-least-32-characters",
        DEMO_MODE="false",
        DEBUG="false",
        ENVIRONMENT="development",
        ALLOWED_HOSTS="127.0.0.1,localhost,test",
        RATE_LIMIT_ENABLED="false",
        DATABASE_POOL_SIZE="30",
        DATABASE_MAX_OVERFLOW="30",
        SENDGRID_API_KEY="mock-benchmark",
        TWILIO_ACCOUNT_SID="mock-benchmark",
        TWILIO_AUTH_TOKEN="",
        STRIPE_SECRET_KEY="",
        STRIPE_WEBHOOK_SECRET="",
        GOOGLE_MAPS_API_KEY="",
        SENTRY_DSN="",
        VAPID_PRIVATE_KEY="",
        VAPID_PUBLIC_KEY="",
    )
    return env


def up():
    specs = [
        (
            NAMES[0],
            [
                "--memory=1g",
                "--cpus=2",
                "-p",
                "127.0.0.1:55439:5432",
                "-e",
                "POSTGRES_DB=axiar_benchmark",
                "-e",
                "POSTGRES_USER=axiar",
                "-e",
                "POSTGRES_PASSWORD=benchmark-only",
                "postgis/postgis:16-3.4",
                "postgres",
                "-c", "shared_preload_libraries=pg_stat_statements",
                "-c", "track_io_timing=on",
                "-c", "track_wal_io_timing=on",
            ],
        ),
        (NAMES[1], ["--memory=256m", "--cpus=1", "-p", "127.0.0.1:56389:6379", "redis:7.2-alpine"]),
        (
            NAMES[2],
            [
                "--memory=1g",
                "--cpus=2",
                "-p",
                "127.0.0.1:59092:9092",
                "-e",
                "KAFKA_NODE_ID=1",
                "-e",
                "KAFKA_PROCESS_ROLES=broker,controller",
                "-e",
                "KAFKA_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093",
                "-e",
                "KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://127.0.0.1:59092",
                "-e",
                "KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER",
                "-e",
                "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT",
                "-e",
                "KAFKA_CONTROLLER_QUORUM_VOTERS=1@localhost:9093",
                "-e",
                "KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1",
                "-e",
                "KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1",
                "-e",
                "KAFKA_TRANSACTION_STATE_LOG_MIN_ISR=1",
                "-e",
                "KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS=0",
                "apache/kafka:3.9.1",
            ],
        ),
    ]
    for name, args in specs:
        existing = docker("ps", "-aq", "--filter", f"name=^/{name}$", capture_output=True, text=True).stdout.strip()
        if existing:
            label = docker(
                "inspect", "--format", '{{index .Config.Labels "axiar.benchmark"}}', name, capture_output=True, text=True
            ).stdout.strip()
            if label != "isolated":
                raise RuntimeError(f"Refusing to touch unlabelled container {name}")
            docker("start", name)
        else:
            docker("run", "-d", "--name", name, "--label", "axiar.benchmark=isolated", *args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["up", "down"])
    args = parser.parse_args()
    if args.action == "up":
        up()
    else:
        for name in NAMES:
            label = docker(
                "inspect", "--format", '{{index .Config.Labels "axiar.benchmark"}}', name, capture_output=True, text=True
            ).stdout.strip()
            if label != "isolated":
                raise RuntimeError(f"Refusing to remove {name}")
            docker("rm", "-f", name)
