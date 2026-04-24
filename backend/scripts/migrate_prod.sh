#!/usr/bin/env bash
# Run Alembic migrations against Cloud SQL via Cloud Run Job
# Usage: ./scripts/migrate_prod.sh <PROJECT_ID> <REGION>
set -euo pipefail

PROJECT_ID="${1:?Usage: $0 <PROJECT_ID> <REGION>}"
REGION="${2:-asia-southeast1}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/aegis-erp/api:latest"
CLOUD_SQL_INSTANCE="${PROJECT_ID}:${REGION}:aegis-erp-db"

echo "Running migrations via Cloud Run Job..."

gcloud run jobs create aegis-migrate \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --command="alembic" \
  --args="upgrade,head" \
  --set-secrets="DATABASE_URL=aegis-database-url:latest,SECRET_KEY=aegis-secret-key:latest" \
  --set-env-vars="ENVIRONMENT=production" \
  --add-cloudsql-instances="${CLOUD_SQL_INSTANCE}" \
  --max-retries=1 \
  --project="${PROJECT_ID}" 2>/dev/null || \
gcloud run jobs update aegis-migrate \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --set-secrets="DATABASE_URL=aegis-database-url:latest,SECRET_KEY=aegis-secret-key:latest" \
  --set-env-vars="ENVIRONMENT=production" \
  --add-cloudsql-instances="${CLOUD_SQL_INSTANCE}" \
  --clear-vpc-connector \
  --project="${PROJECT_ID}"

gcloud run jobs execute aegis-migrate \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --wait

echo "Migrations complete."
