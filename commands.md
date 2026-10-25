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

### Web Portal Workflow (Recommended):

1. **Open Portal**: Have your peer open `http://<HOST_IP_OR_TAILSCALE_IP>:5174` (or `:8000/portal`).
2. **Enroll**: Submit display name and organization.
3. **Approve**: On Host Dashboard (`:5173`), approve the client.
4. **Download Kit**: The client clicks **Download Client Kit (.zip)**.
5. **Run**:
   - **Windows**: Double-click `start.bat` (or run in Command Prompt / PowerShell).
   - **Linux / macOS**: Run `bash start.sh`.

---

### Command-Line Client Workflow:

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
   - **Windows**:
     ```cmd
     cd my-client-kit
     start.bat
     ```
   - **Linux / macOS**:
     ```bash
     cd ./my-client-kit
     bash start.sh
     ```

---

## 3. Launching Federated Training Jobs

### Trigger a Job:

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

### Check Job Status & Collect Results:

```bash
# Check status
curl -H "Authorization: Bearer changeme" http://127.0.0.1:8000/jobs/<JOB_ID>/status

# Collect metrics and evaluate model
curl -X POST -H "Authorization: Bearer changeme" http://127.0.0.1:8000/jobs/<JOB_ID>/collect
```

---

## 4. Tailscale & Remote Network Setup

To allow participants outside your local Wi-Fi to connect:
1. Ensure both your host machine and participant machines are connected to the same Tailscale network (Tailnet).
2. Set your coordinator environment variables in `.env`:
   ```bash
   NEXMESH_SERVER_NAME="<HOST_TAILSCALE_IP>"
   NEXMESH_COORDINATOR_URL="http://<HOST_TAILSCALE_IP>:8000"
   ```
3. Remote clients connect to `http://<HOST_TAILSCALE_IP>:5174` and download kits pre-configured with your Tailscale IP.
4. No router port forwarding or public static IP is required.
