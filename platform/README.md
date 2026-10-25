# NexMesh Coordinator

The first Coordinator slice provides a host-authenticated client registry and an authenticated agent heartbeat API. It uses SQLite by default for local development and keeps the lifecycle state explicit.

## Run locally

From the repository root:

```bash
export NEXMESH_HOST_TOKEN=host-test
export NEXMESH_AGENT_TOKEN=agent-test
export NEXMESH_DATABASE_PATH=platform/nexmesh.db
(cd platform && ../.venv/bin/uvicorn backend.main:app --reload)
```

The API is available at `http://127.0.0.1:8000`. Interactive API documentation is at `/docs`.

## Remote client portal

The participant portal is in `platform/client-frontend`. It supports enrollment
requests, approval status, assigned jobs, task requirement downloads, and
permitted result submission.

```bash
npm --prefix platform/client-frontend install
VITE_API_URL=http://127.0.0.1:8000 \
	npm --prefix platform/client-frontend run dev -- --host 127.0.0.1 --port 5174
```

## Smoke test

```bash
(cd platform && ../.venv/bin/python backend/smoke_test.py)
```

This slice does not provision NVFlare identities or Kubernetes workloads yet. A client reaching `ONLINE` here means the Coordinator lifecycle API accepted an authenticated heartbeat; the later provisioning service must verify the actual NVFlare connection before reporting an operational site.
