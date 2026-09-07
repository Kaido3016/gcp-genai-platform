# DEPLOYMENT.md

**Status: not yet deployed.** Every command below is real and intended to
work, but none has been executed against a live GCP project from this
environment (no network access here — see `AUDIT.md` §4). Run these
yourself and record the actual results; do not treat this document as
proof of a working deployment until you have.

## 1. Local development (no GCP needed)

```bash
cp .env.example .env          # GCP_USE_LIVE_VERTEX_AI=false by default
make install
make dev                      # http://localhost:8080, docs at /docs
make test                     # runs the full test suite against the mock backend
```

## 2. GCP project setup

```bash
export PROJECT_ID=your-gcp-project-id
export REGION=us-central1

gcloud config set project "$PROJECT_ID"

# APIs to enable
gcloud services enable \
  run.googleapis.com \
  aiplatform.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com
```

## 3. Service account (least privilege)

```bash
gcloud iam service-accounts create genai-platform-runner \
  --display-name="GenAI Platform Cloud Run runner"

SA_EMAIL="genai-platform-runner@${PROJECT_ID}.iam.gserviceaccount.com"

# Vertex AI (Gemini + embeddings + Vector Search)
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/aiplatform.user"

# Cloud Storage — scope to the specific bucket, not project-wide, once created (step 4)
gsutil iam ch "serviceAccount:${SA_EMAIL}:roles/storage.objectAdmin" \
  "gs://${PROJECT_ID}-genai-platform-documents"

# Secret Manager
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/secretmanager.secretAccessor"
```

## 4. Cloud Storage bucket

```bash
gsutil mb -l "$REGION" "gs://${PROJECT_ID}-genai-platform-documents"
gsutil uniformbucketlevelaccess set on "gs://${PROJECT_ID}-genai-platform-documents"
```

## 5. Vertex AI Vector Search index + endpoint

```bash
# Create the index (adjust dimensions to match EMBED_OUTPUT_DIMENSIONALITY, default 768)
gcloud ai indexes create \
  --display-name=genai-platform-index \
  --metadata-file=infra/vector_index_metadata.json \
  --region="$REGION"

# Create and deploy a public endpoint (see infra/ for network-restricted alternative)
gcloud ai index-endpoints create \
  --display-name=genai-platform-endpoint \
  --region="$REGION" \
  --public-endpoint-enabled

gcloud ai index-endpoints deploy-index INDEX_ENDPOINT_ID \
  --index=INDEX_ID \
  --deployed-index-id=genai_platform_deployed \
  --region="$REGION"
```

Record the resulting index ID and endpoint ID into `.env`
(`GCP_VECTOR_INDEX_ID`, `GCP_VECTOR_INDEX_ENDPOINT_ID`).

## 6. Build and push the container

```bash
gcloud artifacts repositories create genai-platform \
  --repository-format=docker --location="$REGION"

gcloud builds submit --tag "${REGION}-docker.pkg.dev/${PROJECT_ID}/genai-platform/app:latest"
```

(`make build` / `make docker-run` run the same `Dockerfile` locally for a
quick sanity check before pushing — not run in this environment either,
since it has no Docker daemon and no network to pull the base image; see
`FINAL_AUDIT.md`.)

## 7. Deploy to Cloud Run

```bash
gcloud run deploy genai-platform \
  --image="${REGION}-docker.pkg.dev/${PROJECT_ID}/genai-platform/app:latest" \
  --region="$REGION" \
  --service-account="$SA_EMAIL" \
  --set-env-vars="GCP_USE_LIVE_VERTEX_AI=true,GCP_PROJECT_ID=${PROJECT_ID},GCP_LOCATION=${REGION},GCP_DOCUMENTS_BUCKET=${PROJECT_ID}-genai-platform-documents,GCP_VECTOR_INDEX_ID=<index-id>,GCP_VECTOR_INDEX_ENDPOINT_ID=<endpoint-id>" \
  --no-allow-unauthenticated \
  --min-instances=0 \
  --max-instances=10 \
  --memory=1Gi \
  --cpu=1
```

`--no-allow-unauthenticated` is deliberate: this service has no built-in
end-user auth layer (see `SECURITY.md`), so it should sit behind IAM
invoker permissions or a load balancer with Identity-Aware Proxy rather
than being open on the public internet as-is.

**MCP note:** the MCP server (`docs/MCP.md`) runs as a local subprocess
spawned by the API process itself (`python -m app.mcp.server`) — it needs
no separate Cloud Run service, networking, or IAM entry; it's process-
level, not infrastructure-level. The only requirement is that the
deployed container's Python environment can run `app/mcp/server.py`,
which it can since it ships with the same image (no extra dependencies —
the MCP transport layer is stdlib-only). Set `MCP_ENABLED=false` if you
want to deploy without it for any reason.

## 8. Verification (run these after deploying, not assumed)

```bash
SERVICE_URL=$(gcloud run services describe genai-platform --region="$REGION" --format='value(status.url)')

curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" "$SERVICE_URL/healthz"
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" "$SERVICE_URL/readyz"

# Then exercise the real endpoints (upload -> chat -> agent) and record
# actual latency/behavior in FINAL_AUDIT.md — do not claim this works
# until you've done this.
```

## 9. Rollback

```bash
gcloud run services update-traffic genai-platform --region="$REGION" --to-revisions=PREVIOUS_REVISION=100
```

Cloud Run keeps prior revisions by default, so rollback is a traffic-split
change, not a redeploy — no rebuild needed.

## 10. Cleanup (avoid ongoing billing)

```bash
gcloud run services delete genai-platform --region="$REGION"
gcloud ai index-endpoints undeploy-index INDEX_ENDPOINT_ID --deployed-index-id=genai_platform_deployed --region="$REGION"
gcloud ai index-endpoints delete INDEX_ENDPOINT_ID --region="$REGION"
gcloud ai indexes delete INDEX_ID --region="$REGION"
gsutil -m rm -r "gs://${PROJECT_ID}-genai-platform-documents"
```

Vector Search endpoints in particular bill continuously while deployed —
tear this down promptly after any demo/interview run-through.
