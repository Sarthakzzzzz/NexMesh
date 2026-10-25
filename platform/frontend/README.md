# NexMesh Dashboard

React/Vite host dashboard for the Coordinator.

## Run

From the repository root:

```bash
cd platform/frontend
npm install
VITE_API_URL=http://127.0.0.1:8000 VITE_HOST_TOKEN=host-test npm run dev
```

The Clients view is wired to the current Coordinator API. Jobs and Runs are intentionally staged until their backend endpoints are implemented.
