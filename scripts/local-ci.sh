#!/usr/bin/env bash
# Run selected local checks in disposable Docker services.
# Usage: scripts/local-ci.sh [lint security backend-test frontend e2e build] [--keep]
# Requires Docker; dependencies are cached in named volumes.
set -euo pipefail
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'

cd "$(dirname "$0")/.."
# Stream the working tree into a named volume shared by the job containers.

PROJECT=axiar-ci
NET=axiar-ci-net        # stable external network shared by services + job containers
RUNNER=axiar-ci-runner:local
REPO_VOL=axiar-ci-repo  # holds the streamed working tree inside the Docker VM
SERVICES=(docker compose -p "$PROJECT" -f scripts/ci-services.yml)

KEEP=0
JOBS=()
for a in "$@"; do
  case "$a" in
    --keep) KEEP=1 ;;
    all) JOBS=(lint security backend-test frontend e2e build) ;;
    lint|security|backend-test|frontend|e2e|build) JOBS+=("$a") ;;
    *) echo "unknown arg: $a" >&2; exit 2 ;;
  esac
done
[ ${#JOBS[@]} -eq 0 ] && JOBS=(lint security backend-test frontend e2e build)

# --- shared docker run scaffolding ------------------------------------------
MOUNTS=(
  -v "${REPO_VOL}:/repo"
  -v axiar-ci-pip:/root/.cache/pip
  -v axiar-ci-npm:/root/.npm
  -v axiar-ci-pw:/root/.cache/ms-playwright
)
# Disposable test services are addressed by their Compose service names.
TEST_ENV=(
  -e "DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/axiar_test"
  -e "REDIS_URL=redis://redis:6379"
  -e "SECRET_KEY=test-secret-key-minimum-32-characters-long"
  -e "RATE_LIMIT_ENABLED=false"
  -e "ALLOWED_HOSTS=*"
  -e "STRIPE_SECRET_KEY=sk_test_dummy"
  -e "STRIPE_WEBHOOK_SECRET=whsec_dummy"
  -e "SENDGRID_API_KEY=SG.dummy"
  -e "TWILIO_ACCOUNT_SID=dummy"
  -e "TWILIO_AUTH_TOKEN=dummy"
  -e "TWILIO_PHONE_NUMBER=+1234567890"
  -e "GOOGLE_MAPS_API_KEY=dummy"
  -e "GOOGLE_CLIENT_ID=dummy"
  -e "GOOGLE_CLIENT_SECRET=dummy"
  -e "MICROSOFT_CLIENT_ID=dummy"
  -e "MICROSOFT_CLIENT_SECRET=dummy"
)
E2E_ENV=(
  -e "DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/axiar_test"
  -e "SECRET_KEY=test-secret-key-minimum-32-characters-long"
  -e "RATE_LIMIT_ENABLED=false"
  -e "ALLOWED_HOSTS=*"
  -e "DEMO_MODE=true"
  -e "DEMO_TENANT_SLUG=demo"
  -e "E2E_JWT_SECRET=test-secret-key-minimum-32-characters-long"
  -e "E2E_DATABASE_URL=postgresql://postgres:postgres@postgres:5432/axiar_test"
  -e "E2E_API_URL=http://localhost:8000"
  -e "E2E_BASE_URL=http://localhost:5173"
)

runner() {           # runner <extra docker args...> -- <bash -lc script>
  docker run --rm --network "$NET" "${MOUNTS[@]}" "$@"
}

build_runner_image() {
  docker image inspect "$RUNNER" >/dev/null 2>&1 && return 0
  echo ">> building local-CI runner image ($RUNNER) — one time"
  docker build -t "$RUNNER" -f scripts/Dockerfile.ci scripts
}

ensure_network() {
  docker network inspect "$NET" >/dev/null 2>&1 || { echo ">> creating docker network $NET"; docker network create "$NET" >/dev/null; }
}

seed_repo() {
  echo ">> seeding working tree into volume $REPO_VOL"
  docker volume rm "$REPO_VOL" >/dev/null 2>&1 || true
  docker volume create "$REPO_VOL" >/dev/null
  docker create --name axiar-ci-seed -v "${REPO_VOL}:/repo" "$RUNNER" tail -f /dev/null >/dev/null
  # Exclude local environments, VCS state and generated files from the volume.
  tar -cf - --ignore-failed-read \
    --exclude=.git --exclude=node_modules --exclude=.venv --exclude='.env*' \
    --exclude=__pycache__ --exclude=.pytest_cache --exclude=.mypy_cache --exclude=.ruff_cache \
    --exclude=dist --exclude=playwright-report --exclude=test-results \
    . | docker cp - axiar-ci-seed:/repo
  docker rm -f axiar-ci-seed >/dev/null
}

services_up() {
  echo ">> starting CI services (postgres, redis, stripe-mock)"
  "${SERVICES[@]}" up -d
  # The postgis image runs its init scripts against a temporary server, then shuts
  # it down and restarts for real — so a single early pg_isready is not enough
  # (extension commands can hit "database system is shutting down"). Retry the
  # extension creation itself until it succeeds: a clean CREATE EXTENSION proves
  # the real server is up. Loud failure if it never comes up.
  echo ">> waiting for postgres + creating extensions"
  local ok=0
  for _ in $(seq 1 45); do
    if "${SERVICES[@]}" exec -T postgres psql -U postgres -d axiar_test \
        -c "CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";" >/dev/null 2>&1; then
      ok=1; break
    fi
    sleep 2
  done
  [ "$ok" = 1 ] || { echo "!! postgres did not become ready after 90s" >&2; return 1; }
}

services_down() { [ "$KEEP" -eq 1 ] || { echo ">> tearing down CI services"; "${SERVICES[@]}" down -v >/dev/null 2>&1 || true; }; }

# Each GitHub job gets its own fresh Postgres AND Redis service; locally the jobs
# share both. Recreate the DB before every DB-consuming job to mirror that
# isolation — without this, pytest's teardown drops the ORM tables but
# alembic_version survives, so a later job's `alembic upgrade head` no-ops onto
# an empty schema (bit e2e 2026-07-14). Redis must be flushed in the same step:
# TenantMiddleware caches tenant-slug resolution for 300s, so a fresh DB's newly
# created "default" tenant (a new UUID) can be shadowed by a stale cached UUID
# from the previous job's (now-dropped) DB — registration writes the real
# tenant, login resolves the stale cached one, and they mismatch ("User not
# found in tenant"). Bit the e2e job right after backend-test, 2026-07-14.
reset_db() {
  "${SERVICES[@]}" exec -T postgres psql -U postgres -d postgres \
    -c "DROP DATABASE IF EXISTS axiar_test WITH (FORCE);" -c "CREATE DATABASE axiar_test;" >/dev/null
  "${SERVICES[@]}" exec -T postgres psql -U postgres -d axiar_test \
    -c "CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";" >/dev/null
  "${SERVICES[@]}" exec -T redis redis-cli FLUSHALL >/dev/null
}

need_services() { for j in "${JOBS[@]}"; do [[ "$j" == backend-test || "$j" == e2e ]] && return 0; done; return 1; }

# --- named checks ------------------------------------------------------------
job_lint() {
  echo "==================== backend-lint ===================="
  runner -w /repo/backend "$RUNNER" bash -euo pipefail -c '
    pip install -q black flake8 isort mypy bandit
    black --check app tests
    isort --check-only app tests
    flake8 app tests --count --statistics
    mypy app/core --ignore-missing-imports
    mypy app --ignore-missing-imports
  '
}

job_security() {
  echo "==================== backend-security ===================="
  runner -w /repo "$RUNNER" bash -euo pipefail -c '
    pip install -q bandit pip-audit detect-secrets
    cd backend
    bandit -r app -c pyproject.toml -f json -o ../bandit-report.json
    bandit -r app -c pyproject.toml
    cd /repo
    pip-audit -r backend/requirements.txt
    detect-secrets scan --baseline .secrets.baseline
  '
}

job_backend_test() {
  echo "==================== backend-test ===================="
  reset_db
  runner -w /repo/backend "${TEST_ENV[@]}" "$RUNNER" bash -euo pipefail -c '
    pip install -q -r requirements.txt
    pip install -q pytest pytest-cov pytest-asyncio
    alembic upgrade head
    alembic check
    pytest tests/ -v --cov=app --cov-report=xml --cov-report=term
  '
}

job_frontend() {
  echo "==================== frontend-ci ===================="
  runner -w /repo/frontend "$RUNNER" bash -euo pipefail -c '
    npm ci
    npm run lint
    npm test
    npm run build
  '
}

job_e2e() {
  echo "==================== e2e-tests ===================="
  reset_db
  runner -w /repo "${E2E_ENV[@]}" "$RUNNER" bash -euo pipefail -c '
    cd /repo/backend
    pip install -q -r requirements.txt
    alembic upgrade head
    python -m scripts.seed_demo
    nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/backend.log 2>&1 &
    for i in $(seq 1 30); do curl -sf http://localhost:8000/api/v1/health && break; sleep 1; done
    cd /repo/frontend
    npm ci
    # Use the installed Node runtime when refreshing browser-system dependencies.
    rm -f /etc/apt/sources.list.d/nodesource.list /etc/apt/sources.list.d/nodesource.sources
    npx playwright install --with-deps chromium
    VITE_DEMO_MODE=true VITE_API_URL=http://localhost:8000 npm run build
    nohup npm run preview -- --host 0.0.0.0 --port 5173 > /tmp/frontend.log 2>&1 &
    for i in $(seq 1 30); do curl -sf http://localhost:5173 && break; sleep 1; done
    E2E_DEMO_MODE=true npx playwright test || { echo "----- backend.log -----"; cat /tmp/backend.log; echo "----- frontend.log -----"; cat /tmp/frontend.log; exit 1; }
  '
}

job_build() {
  echo "==================== build (docker image) ===================="
  docker build -t axiar-backend:local backend
}

# --- run ---------------------------------------------------------------------
trap services_down EXIT
build_runner_image
ensure_network
seed_repo
need_services && services_up

FAILED=()
for j in "${JOBS[@]}"; do
  case "$j" in
    lint)         job_lint         || FAILED+=("$j") ;;
    security)     job_security     || FAILED+=("$j") ;;
    backend-test) job_backend_test || FAILED+=("$j") ;;
    frontend)     job_frontend     || FAILED+=("$j") ;;
    e2e)          job_e2e          || FAILED+=("$j") ;;
    build)        job_build        || FAILED+=("$j") ;;
  esac
done

echo "============================================================"
if [ ${#FAILED[@]} -eq 0 ]; then
  echo "LOCAL CI: PASS (${JOBS[*]})"
else
  echo "LOCAL CI: FAIL -> ${FAILED[*]}"
  exit 1
fi
