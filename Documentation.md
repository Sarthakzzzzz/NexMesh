# Documentation

## Overview

NexMesh uses NVIDIA FLARE 2.9 and PyTorch to implement a privacy-preserving federated-learning platform. 

The central NVFlare Server and Admin services run in Kubernetes (Kind) on the host machine, while clients run as lightweight remote participants directly on host operating systems (**Windows, Linux, or macOS**) with native GPU acceleration and automatic CPU fallback.

---

## Architecture & Workflows

### 1. Remote Enrollment Workflow

```text
[ Remote Participant ]              [ NexMesh Coordinator ]             [ NVFlare PKI ]
        |                                       |                              |
        |--- 1. POST /enrollments ------------->|                              |
        |    (Name, Org, Capabilities)          |                              |
        |<-- 2. Returns PENDING + token --------|                              |
        |                                       |                              |
        |                                       | [Host reviews & approves]    |
        |                                       |--- 3. Provision client kit ->|
        |                                       |<-- 4. Signed kit & certs ----|
        |                                       |                              |
        |--- 5. GET /enrollments/{id}/kit ----->|                              |
        |<-- 6. Returns self-contained zip -----|                              |
        |    (start.bat, start.sh, agent.py)    |                              |
        |                                       |                              |
        |--- 7. start.bat / bash start.sh ----->|                              |
        |    (Live Heartbeat: ONLINE)           |                              |
```

1. **Self-Registration**: The client submits registration details to `POST /enrollments` or via the Client Portal (`:5174`).
2. **Pending Isolation**: The client is stored with status `PENDING`. No files or directories are created on disk.
3. **Host Approval**: The host approves the client on the Host Dashboard (`:5173`).
4. **Dynamic Provisioning**: The backend calls the provisioning service to generate an isolated startup kit (`prod_XX/<client-id>`) signed by the federation root CA in `state/cert.json`.
5. **Direct Delivery**: The client downloads the bundled kit zip containing certificates, `agent.py`, `requirements.txt`, `sitecustomize.py`, and pre-configured startup scripts (`start.bat` for Windows, `start.sh` for Linux/macOS).
6. **Cross-Platform Connection**: The client runs `start.bat` (Windows) or `bash start.sh` (Linux/macOS), connecting securely over mutual TLS to NVFlare port `8002` and streaming heartbeats to port `8000`.
7. **Cleanup on Departure**: When a client is deleted or leaves (`DELETE /clients/{id}`), its provisioned kit directory and database records are completely wiped.

---

### 2. Federated Training & Aggregation Cycle

For each job submitted via `POST /jobs/nvflare`:

1. **Initial Model Broadcast**: NVFlare initializes `MNISTCNN` weights and broadcasts them to all assigned remote clients.
2. **Local Training**:
   - Each client trains for the requested `local_epochs` using its local dataset.
   - Automatically uses NVIDIA GPU (CUDA) if present; falls back to CPU seamlessly if not.
3. **Model Update Transmission**: Each client computes model parameter differences ($\Delta W = W_{\text{local}} - W_{\text{global}}$) and sends them to the server over mutual TLS.
4. **FedAvg Aggregation**: The server aggregates all received client deltas using `InTimeAccumulateWeightedAggregator`.
5. **Global Model Update & Persistence**: `FullModelShareableGenerator` applies the aggregated deltas to update the global model weights ($W_{\text{global}} \leftarrow W_{\text{base}} + \Delta W$). `PTFileModelPersistor` persists checkpoints to disk.
6. **Server-Side Global Evaluation**: `ServerMNISTEvaluator` evaluates the updated global model on the server test dataset (10,000 samples) at round completion (`AppEventType.ROUND_DONE`) and records metrics.
7. **Cycle Repeat**: `ScatterAndGather` broadcasts the updated global model for the next round until `num_rounds` is complete.

---

### 3. Cross-Platform Windows Execution & Path Safety

NVFlare's standard `ProcessJobLauncher` splits subprocess commands with `posix=True`, which strips backslashes (`\`) from native Windows paths. To ensure 100% native execution on Windows without WSL or bash:
- **`sitecustomize.py` Hook**: Bundled into every client kit. When Python starts on Windows, it automatically patches `shlex.split` with `posix=False`, preserving full Windows paths.
- **Direct Python Invocation**: `agent.py` invokes NVFlare training via `sys.executable` directly, ensuring Python virtual environments on Windows (`Scripts\python.exe`) and Unix (`bin/python`) work identically.

---

## Data Boundaries & Privacy Guarantees

- **Local Data Only**: Raw client training datasets remain strictly on each participant's machine.
- **No Data in Transit**: Only model weights/gradients and loss/accuracy metrics are transmitted across the network.
- **Isolated Mounts**: In the host Kind harness, the server pod only mounts `/data/server_test` (evaluation only) and `/results`. Client training splits are never mounted on the server.
- **Server Separation**: The central server never has filesystem or runtime access to remote participant data.

---

## Verified Benchmarks

The current implementation has been verified with end-to-end training runs:
- **Client Hardware**: Tested on NVIDIA RTX 5050 Laptop GPU (CUDA) and CPU fallback.
- **Dataset**: MNIST classification split across distributed sites.
- **Model**: Convolutional Neural Network (`MNISTCNN` with 2 convolutional layers and 2 linear layers).
- **Results**:
  - Round 0 Server Test Accuracy: **`98.75%`** (loss: 0.0379)
  - Round 1 Server Test Accuracy: **`99.01%`** (loss: 0.0292)
  - Round 2 Server Test Accuracy: **`98.87%`** (loss: 0.0375)
  - Round 3 Server Test Accuracy: **`99.04%`** (loss: 0.0388)
  - Round 4 Server Test Accuracy: **`99.24%`** (loss: 0.0333)
  - Final Checkpoint: [`workspace/fedlearn/results/final_global_model.pt`](workspace/fedlearn/results/final_global_model.pt)
