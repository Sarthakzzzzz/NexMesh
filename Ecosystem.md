# NexMesh Ecosystem Overview

## Core Components

- **NVIDIA FLARE 2.9**: Federated learning orchestration engine managing task scheduling, secure mutual TLS communication, aggregation, and workflow execution.
- **PyTorch**: Deep learning framework used for CNN model architecture (`MNISTCNN`), dataset loading, and local model training.
- **Kind (Kubernetes in Docker)**: Minimal development harness hosting the NVFlare Server and Admin pods.
- **NexMesh Coordinator**: FastAPI backend managing dynamic client enrollment, PKI provisioning, job lifecycle, and result collection.
- **Client Agent**: Standalone Python agent running directly on participant machines (**Windows, Linux, or macOS**), abstracting NVFlare execution and providing live heartbeats without container requirements.
- **Web Dashboards**:
  - **Host Dashboard** (React + Vite on port `5173`): Client approval, job monitoring, and metrics visualization.
  - **Client Portal** (React + Vite on port `5174`): Participant self-registration, status polling, and one-click kit download.

---

## Network & Runtime Topology

```text
[ Remote Client 1 ] (RTX 5050 / Linux)
      |
      |-- (Mutual TLS :8002 & REST :8000)
      v
+--------------------------------------------------------------+
|                    NexMesh Host Node                         |
|                                                              |
|  FastAPI Backend (:8000)      Host Dashboard UI (:5173)      |
|  Participant Portal (:5174)   SQLite DB (clients & jobs)     |
|                                                              |
|  +--------------------------------------------------------+  |
|  |                 Kind Kubernetes Cluster                |  |
|  |                                                        |  |
|  |   [ Pod: nvflare-server ]       [ Pod: nvflare-admin ] |  |
|  |   - WFCommServer (:8002)        - Flare Admin Session  |  |
|  |   - InTimeAccumulateAggregator  - Job Submission CLI   |  |
|  |   - ServerMNISTEvaluator                               |  |
|  |   - Volume: /data/server_test                          |  |
|  |   - Volume: /results (mapped to host)                  |  |
|  +--------------------------------------------------------+  |
+--------------------------------------------------------------+
      ^
      |-- (Mutual TLS :8002 & REST :8000)
      |
[ Remote Client 2 ] (Windows / CPU / Remote via Tailscale)
```

---

## Directory Roles & Boundaries

- `commands/`: Single-command operational shell scripts for developers and hosts.
- `jobs/`: Self-contained NVFlare federated job definitions, configurations, and evaluator components.
- `k8s/`: Kubernetes deployment manifests for server and admin pods.
- `platform/backend/`: Coordinator database, REST APIs, and NVFlare certificate provisioning engine.
- `platform/agent/`: Standalone participant runner, startup scripts (`start.bat`, `start.sh`), and dataset generators.
- `platform/frontend/`: React Host Dashboard.
- `platform/client-frontend/`: React Participant Portal.
- `workspace/fedlearn/`: NVFlare root CA, base participant kits, test datasets, and output results.
