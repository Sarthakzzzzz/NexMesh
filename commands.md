# NexMesh Commands & Operational Guide

All common workflows are available as executable scripts in [`commands/`](commands/).

---

## 1. Quick Service Launch

Run each script in a separate terminal from the project root:

```bash
# 1. Start Kind K8s Cluster with NVFlare Server & Admin
./commands/1_start_k8s.sh

# 2. Start Coordinator Backend API (Port 8000)
./commands/2_start_backend.sh

# 3. Start Host Coordinator Dashboard (Port 5173)
./commands/3_start_host_dashboard.sh

# 4. Start Remote Participant Portal (Port 5174)
./commands/4_start_client_portal.sh
```

To stop all background processes:
```bash
./commands/stop_all.sh
```

---

## 2. Remote Client Workflow

### Registering and Starting a Client:

1. **Enroll Client**:
   ```bash
   curl -X POST http://<HOST_IP>:8000/enrollments \
     -H "Content-Type: application/json" \
     -d '{"display_name": "client-1", "organization": "partner", "mode": "remote_participant"}'
   ```
   Save the returned `client_id` and `client_token`.

2. **Approve on Host Dashboard**:
   Open [`http://localhost:5173`](http://localhost:5173), navigate to **Pending Clients**, and click **Approve**.

3. **Download Client Kit**:
   ```bash
   curl -H "x-nexmesh-client-token: <CLIENT_TOKEN>" \
     http://<HOST_IP>:8000/enrollments/<CLIENT_ID>/kit \
     -o <CLIENT_ID>-kit.zip
   
   unzip <CLIENT_ID>-kit.zip -d ./my-client-kit
   ```

4. **Launch Agent**:
   ```bash
   cd ./my-client-kit
   bash start.sh
   ```
   *(Or specify a custom dataset: `bash start.sh /path/to/my_mnist.pt`)*

---

## 3. Submitting Federated Jobs

### Submit via REST API:

```bash
curl -X POST http://127.0.0.1:8000/jobs/nvflare \
  -H "Authorization: Bearer changeme" \
  -H "Content-Type: application/json" \
  -d '{
    "participants": ["<CLIENT_ID>"],
    "num_rounds": 2,
    "local_epochs": 1,
    "batch_size": 64
  }'
```

### Check Job Status:

```bash
curl -s -H "Authorization: Bearer changeme" \
  http://127.0.0.1:8000/jobs/<JOB_ID>/status
```

### Collect Job Results:

```bash
curl -s -X POST -H "Authorization: Bearer changeme" \
  http://127.0.0.1:8000/jobs/<JOB_ID>/collect
```

---

## 4. Inspecting Output Models & Metrics

The latest global model and evaluation metrics are saved at:

```bash
# View server evaluation metrics summary
cat workspace/fedlearn/results/summary.json

# View per-round evaluation lines
cat workspace/fedlearn/results/server_test_metrics.jsonl

# Inspect the PyTorch model weights
python3 -c "
import torch
ckpt = torch.load('workspace/fedlearn/results/final_global_model.pt', map_location='cpu', weights_only=True)
print('Checkpoint keys:', list(ckpt.keys()))
for k, v in ckpt['model_state_dict'].items():
    print(f'  {k:30s} shape: {list(v.shape)}')
"
```

---

## 5. Automated Integration Test

To verify the entire pipeline automatically:

```bash
./commands/6_test_workflow.sh
```
This runs the integration smoke test, validating client enrollment, host approval, kit packaging, and API connectivity.
