# NexMesh

NexMesh is a decentralized federated-learning platform where independent remote machines collaborate to train deep learning models while keeping their raw training datasets strictly local. 

The central coordinator and NVFlare server run inside a minimal Kubernetes/Kind cluster, while remote client participants run directly on their own host machines (**Windows, Linux, or macOS**) with automatic GPU acceleration and CPU fallback — without requiring Kubernetes or container runtimes on client devices.

---

## Architecture Overview

```text
[ Remote Client A ] (Windows / CPU)   <----+
                                           |  Mutual TLS &
[ Remote Client B ] (Linux / RTX 5050) <---+  REST Protocol (Tailscale / LAN / WAN)
                                           |
[ Remote Client N ] (macOS / Metal/CPU)<---+
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
   |  |   - Service NodePort (:8002)                        |  |
   |  +-----------------------------------------------------+  |
   +-----------------------------------------------------------+
```

---

## Key Features

- **Decentralized Data Privacy**: Raw training data never leaves the client's local machine. Only model weight updates (deltas) and evaluation metrics are transmitted.
- **Cross-Platform Native Execution**:
  - Full native support for **Windows** (Command Prompt / PowerShell via `start.bat`), **Linux**, and **macOS** (`start.sh`).
  - No Docker, Kubernetes, WSL, or Git Bash required on remote client nodes.
- **Hardware-Agnostic & Auto-Switching**:
  - Automatically detects NVIDIA GPUs (CUDA) across heterogeneous devices.
  - Gracefully falls back to CPU if no GPU is detected, adjusting pinned memory and worker threads dynamically.
- **Zero-Config Remote Connectivity via Tailscale / LAN**:
  - Services listen on `0.0.0.0` to allow secure remote participation over Tailscale mesh networks or private LANs without public IP addresses or router port forwarding.
  - Coordinator automatically embeds the host's network address into client kits.
- **Dynamic Onboarding & Lifecycle**:
  - Remote participants register via the web Client Portal or REST API.
  - Clients start in `PENDING` state with zero disk footprint.
  - Once the Host approves the client on the Host Dashboard, the backend dynamically provisions an isolated startup kit with CA-signed mutual TLS certificates.
  - Complete disk and database cleanup when a client leaves or is deleted.
- **Self-Contained Client Startup Kit**:
  - Downloaded kit zip includes `requirements.txt`, `agent.py`, `generate_dataset.py`, `sitecustomize.py`, `start.bat` (Windows), and `start.sh` (Linux/macOS).
  - Runs in a single click or command.
- **Automated Server-Side Evaluation**:
  - Evaluates aggregated global model weights after every round on an independent test dataset (10,000 MNIST test samples).
  - Deduplicated metric logging saved to `summary.json`, `server_test_metrics.jsonl`, and outputs global checkpoint `final_global_model.pt`.

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
- **Client Portal**: `http://<HOST_IP>:5174` (or `http://<HOST_IP>:8000/portal`)

---

### 2. Onboarding a Remote Participant

#### **Step A: Register**
Have your remote peer open the Client Portal in their browser:
```text
http://<HOST_IP_OR_TAILSCALE_IP>:5174
```
They enter their Display Name and Organization and click **Enroll**.

#### **Step B: Approve**
Open your Host Dashboard at `http://localhost:5173`, navigate to **Pending Clients**, and click **Approve**.

#### **Step C: Download & Run**

##### **On Windows (Command Prompt / PowerShell)**:
1. Download `<client-id>-kit.zip` from the Client Portal.
2. Extract the `.zip` archive.
3. Open Command Prompt or PowerShell in the extracted folder and run:
   ```cmd
   start.bat
   ```
   *(or simply double-click `start.bat`)*

##### **On Linux / macOS**:
1. Download `<client-id>-kit.zip` from the Client Portal.
2. Extract and run:
   ```bash
   unzip <client-id>-kit.zip -d client-kit
   cd client-kit
   bash start.sh
   ```

The startup scripts automatically:
- Create a local Python virtual environment (`.venv`).
- Install all dependencies from `requirements.txt`.
- Download a local partition of MNIST (`dataset/mnist.pt`) if not already present.
- Detect GPU (CUDA) or fall back to CPU.
- Launch the agent and establish an encrypted mTLS session with the host.

---

### 3. Launching Federated Training

Once participants show **ONLINE** on the Host Dashboard, trigger training:

#### **Via Host Dashboard**:
Click **New Training Job**, select the connected clients, set rounds and local epochs, and click **Launch Job**.

#### **Via REST API (curl)**:
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
- Server evaluation metrics are saved in [`workspace/fedlearn/results/summary.json`](workspace/fedlearn/results/summary.json).

---

## Verified Benchmarks

The current implementation has been verified with multi-round training runs across heterogeneous machines:
- **Participant Devices**: NVIDIA RTX 5050 Laptop GPU (CUDA) + CPU fallback.
- **Model**: `MNISTCNN` (Convolutional Neural Network).
- **Test Dataset**: 10,000 independent MNIST test samples evaluated centrally on the server.
- **Accuracy Progression**:
  - Round 0: **`98.75%`** (loss: 0.0379)
  - Round 1: **`99.01%`** (loss: 0.0292)
  - Round 2: **`98.87%`** (loss: 0.0375)
  - Round 3: **`99.04%`** (loss: 0.0388)
  - Round 4: **`99.24%`** (loss: 0.0333)

---

## Documentation Links

- [`Documentation.md`](Documentation.md) — Workflow, privacy boundaries, and architecture details.
- [`commands.md`](commands.md) — Complete operational reference and command recipes.
- [`Ecosystem.md`](Ecosystem.md) — Component deep-dive and network topology.
- [NVFlare 2.9 API Reference](https://nvflare.readthedocs.io/en/2.9.0/apidocs/modules.html) — Official NVFlare documentation.
