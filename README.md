# NexMesh

NexMesh is a decentralized federated-learning platform where independent remote machines collaborate to train deep learning models while keeping their raw training datasets strictly local. 

The central coordinator and NVFlare server run inside a minimal Kubernetes/Kind cluster, while remote client participants run directly on their own host machines (Linux/macOS) with automatic GPU acceleration and CPU fallback — without requiring Kubernetes or container runtimes on client devices.

---

## Architecture Overview

```text
[ Remote Client A ] (Host OS / GPU) <----+
                                         |  Mutual TLS &
[ Remote Client B ] (Host OS / GPU) <----+  REST Protocol
                                         |
[ Remote Client N ] (Host OS / CPU) <----+
                                         |
                                         v
   +-----------------------------------------------------------+
   |                  NexMesh Host (Coordinator)               |
   |                                                           |
   |  Host Dashboard (:5173)   <--->  Coordinator API (:8000)  |
   |  Client Portal  (:5174)                 |                 |
   |                                         v                 |
   |  +-----------------------------------------------------+  |
   |  |            Kind Kubernetes Cluster                  |  |
   |  |                                                     |  |
   |  |   [ NVFlare Server ]         [ NVFlare Admin ]      |  |
   |  |   - FedAvg Aggregator        - Job Orchestration    |  |
   |  |   - Global Model Persistor   - Admin API Session    |  |
   |  |   - Test Set Evaluator                              |  |
   |  +-----------------------------------------------------+  |
   +-----------------------------------------------------------+
```

---

## Key Features

- **Decentralized Data Privacy**: Raw training data never leaves the client's local machine. Only model weight updates (deltas) and evaluation metrics are transmitted.
- **Dynamic Onboarding & Lifecycle**:
  - Remote participants register via the web Client Portal or REST API.
  - Clients start in `PENDING` state with zero disk footprint.
  - Once the Host approves the client on the Host Dashboard, the backend dynamically provisions an isolated startup kit with CA-signed mutual TLS certificates.
  - Complete disk and database cleanup when a client leaves or is deleted.
- **Self-Contained Client Startup Kit**:
  - Downloaded kit zip includes `requirements.txt`, `agent.py`, `generate_dataset.py`, and a pre-configured `start.sh` script.
  - Runs in a single command (`bash start.sh`).
- **Hardware-Agnostic & Auto-Switching**:
  - Automatically detects NVIDIA GPUs (CUDA) across heterogeneous devices.
  - Gracefully falls back to CPU if no GPU is detected, adjusting pinned memory and worker threads automatically.
- **Automated Server-Side Evaluation**:
  - Evaluates aggregated global model weights after every round on an independent test dataset (e.g., 10,000 MNIST test samples).
  - Saves metrics to `summary.json`, `server_test_metrics.jsonl`, and outputs global checkpoint `final_global_model.pt`.

---

## Repository Structure

```text
├── commands/                   # Ready-to-run lifecycle shell scripts
│   ├── 1_start_k8s.sh          # Start Kind cluster & NVFlare server/admin
│   ├── 2_start_backend.sh      # Start NexMesh Coordinator API (:8000)
│   ├── 3_start_host_dashboard.sh # Start Host UI Dashboard (:5173)
│   ├── 4_start_client_portal.sh# Start Remote Client Portal (:5174)
│   ├── 5_start_remote_client.sh# Launch local remote client agent
│   ├── 6_test_workflow.sh      # Run end-to-end integration test
│   └── stop_all.sh             # Graceful teardown of all services
├── jobs/                       # NVFlare job definitions and recipes
│   └── fedavg_nn/              # PyTorch FedAvg CNN pipeline
│       ├── job.py              # Dynamic job submission generator
│       ├── train.py            # Client-side model & local trainer
│       ├── server_evaluator.py # Server global evaluator component
│       └── app/custom/         # Configuration & deployment templates
├── k8s/                        # Kubernetes deployment manifests
│   ├── nvflare-server.yaml     # Server & Admin deployment manifest
│   └── nvidia-device-plugin.yaml # Time-sliced GPU device plugin
├── platform/                   # Coordinator platform services & UIs
│   ├── backend/                # FastAPI coordinator & provisioning service
│   ├── frontend/               # Host Dashboard (React + Vite)
│   ├── client-frontend/        # Participant Onboarding Portal (React + Vite)
│   └── agent/                  # Standalone client agent runner & scripts
└── workspace/fedlearn/         # Provisioning root, certs, datasets, results
    ├── datasets/               # Client training splits
    ├── server_test/            # Server evaluation dataset
    └── results/                # Output global models and metrics
```

---

## Quickstart Guide

### 1. Host Setup & Startup

Run the numbered scripts in `commands/`:

```bash
# Terminal 1: Boot Kind cluster with NVFlare Server & Admin
./commands/1_start_k8s.sh

# Terminal 2: Start Coordinator Backend (Port 8000)
./commands/2_start_backend.sh

# Terminal 3: Start Host Dashboard (Port 5173)
./commands/3_start_host_dashboard.sh

# Terminal 4: Start Participant Portal (Port 5174)
./commands/4_start_client_portal.sh
```

- **Host Dashboard**: [`http://localhost:5173`](http://localhost:5173) (Token: `changeme`)
- **Coordinator API**: [`http://localhost:8000/docs`](http://localhost:8000/docs)
- **Client Portal**: [`http://<HOST_IP>:5174`](http://<HOST_IP>:5174)

---

### 2. Onboarding a Remote Participant

1. **Register**: Your friend opens the Client Portal at `http://<HOST_IP>:5174` (or via VPN/Tailscale) and clicks **Enroll**.
2. **Approve**: Open the Host Dashboard at `http://localhost:5173` and click **Approve** on the pending client.
3. **Download & Run**:
   Your friend downloads their kit zip from the portal and runs:
   ```bash
   unzip <client-id>-kit.zip -d client-kit
   cd client-kit
   bash start.sh
   ```
   The `start.sh` script automatically creates `.venv`, installs requirements, fetches sample data (if needed), detects GPU/CPU, and connects to the coordinator.

---

### 3. Launching Federated Training

From the Host Dashboard (or via API):

```bash
curl -X POST http://127.0.0.1:8000/jobs/nvflare \
  -H "Authorization: Bearer changeme" \
  -H "Content-Type: application/json" \
  -d '{
    "participants": ["<CLIENT_1_ID>", "<CLIENT_2_ID>"],
    "num_rounds": 5,
    "local_epochs": 1,
    "batch_size": 64
  }'
```

All selected clients train in parallel on their respective hardware. Once completed:
- The aggregated global model is saved at [`workspace/fedlearn/results/final_global_model.pt`](workspace/fedlearn/results/final_global_model.pt).
- Server evaluation metrics are available in [`workspace/fedlearn/results/summary.json`](workspace/fedlearn/results/summary.json).

---

## Documentation

- [`Documentation.md`](Documentation.md) — Workflow, data boundaries, and verification.
- [`commands.md`](commands.md) — Complete CLI reference and command recipes.
- [`Ecosystem.md`](Ecosystem.md) — Architecture and component deep-dive.
- [NVFlare 2.9 API Reference](https://nvflare.readthedocs.io/en/2.9.0/apidocs/modules.html) — Official NVFlare documentation.

# Terminal 4: Start Participant Portal (Port 5174)
./commands/4_start_client_portal.sh
```

- **Host Dashboard**: [`http://localhost:5173`](http://localhost:5173) (Token: `changeme`)
- **Coordinator API**: [`http://localhost:8000/docs`](http://localhost:8000/docs)
- **Client Portal**: [`http://<HOST_IP>:5174`](http://<HOST_IP>:5174)

---

### 2. Onboarding a Remote Participant

1. **Register**: Your friend opens the Client Portal at `http://<HOST_IP>:5174` (or via VPN/Tailscale) and clicks **Enroll**.
2. **Approve**: Open the Host Dashboard at `http://localhost:5173` and click **Approve** on the pending client.
3. **Download & Run**:
   Your friend downloads their kit zip from the portal and runs:
   ```bash
   unzip <client-id>-kit.zip -d client-kit
   cd client-kit
   bash start.sh
   ```
   The `start.sh` script automatically creates `.venv`, installs requirements, fetches sample data (if needed), detects GPU/CPU, and connects to the coordinator.

---

### 3. Launching Federated Training

From the Host Dashboard (or via API):

```bash
curl -X POST http://127.0.0.1:8000/jobs/nvflare \
  -H "Authorization: Bearer changeme" \
  -H "Content-Type: application/json" \
  -d '{
    "participants": ["<CLIENT_1_ID>", "<CLIENT_2_ID>"],
    "num_rounds": 5,
    "local_epochs": 1,
    "batch_size": 64
  }'
```

All selected clients train in parallel on their respective hardware. Once completed:
- The aggregated global model is saved at [`workspace/fedlearn/results/final_global_model.pt`](workspace/fedlearn/results/final_global_model.pt).
- Server evaluation metrics are available in [`workspace/fedlearn/results/summary.json`](workspace/fedlearn/results/summary.json).

---

## Documentation

- [`Documentation.md`](Documentation.md) — Workflow, data boundaries, and verification.
- [`commands.md`](commands.md) — Complete CLI reference and command recipes.
- [`Ecosystem.md`](Ecosystem.md) — Architecture and component deep-dive.
- [NVFlare 2.9 API Reference](https://nvflare.readthedocs.io/en/2.9.0/apidocs/modules.html) — Official NVFlare documentation.

