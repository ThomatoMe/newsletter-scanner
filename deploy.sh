#!/bin/bash
# Newsletter Scanner - deploy na Google Cloud Run
# Spusť v Cloud Shellu

set -e

PROJECT_ID="thomitko-project-sand-box"
REGION="europe-west1"
JOB_NAME="newsletter-scanner"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/cloud-run/$JOB_NAME"

echo "=== 1. Nastavuji GCP projekt ==="
gcloud config set project $PROJECT_ID

echo "=== 2. Povoluji potřebné API ==="
gcloud services enable \
  artifactregistry.googleapis.com \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com

echo "=== 3. Vytvářím Artifact Registry repo (pokud neexistuje) ==="
gcloud artifacts repositories create cloud-run \
  --repository-format=docker \
  --location=$REGION \
  --description="Docker images pro Cloud Run" \
  2>/dev/null || echo "  (repo už existuje)"

echo "=== 4. Konfiguruji Docker auth ==="
gcloud auth configure-docker $REGION-docker.pkg.dev --quiet

echo "=== 5. Builduji a pushuji Docker image ==="
docker build -t $IMAGE .
docker push $IMAGE

echo "=== 6. Vytvářím Cloud Run Job ==="
gcloud run jobs create $JOB_NAME \
  --image=$IMAGE \
  --region=$REGION \
  --memory=1Gi \
  --cpu=1 \
  --max-retries=1 \
  --task-timeout=300s \
  --set-secrets="GMAIL_APP_PASSWORD=gmail-app-password:latest" \
  2>/dev/null || \
gcloud run jobs update $JOB_NAME \
  --image=$IMAGE \
  --region=$REGION \
  --memory=1Gi \
  --cpu=1 \
  --max-retries=1 \
  --task-timeout=300s \
  --set-secrets="GMAIL_APP_PASSWORD=gmail-app-password:latest"

echo "=== 7. Vytvářím Cloud Scheduler (denně v 8:00 CET) ==="
# Získání service account pro Cloud Run invoker
SA_EMAIL=$(gcloud iam service-accounts list --format="value(email)" --filter="displayName:Compute Engine default" 2>/dev/null | head -1)

gcloud scheduler jobs create http $JOB_NAME-daily \
  --location=$REGION \
  --schedule="0 8 * * *" \
  --time-zone="Europe/Prague" \
  --uri="https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/$JOB_NAME:run" \
  --http-method=POST \
  --oauth-service-account-email=$SA_EMAIL \
  2>/dev/null || echo "  (scheduler job už existuje)"

echo ""
echo "=== HOTOVO ==="
echo "Cloud Run Job: $JOB_NAME"
echo "Scheduler: denně v 8:00 CET"
echo ""
echo "Ruční spuštění:"
echo "  gcloud run jobs execute $JOB_NAME --region=$REGION"
