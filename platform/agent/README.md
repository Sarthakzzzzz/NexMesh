# NexMesh Client Agent

Join a NexMesh federation without any manual NVFlare setup.

## Requirements

- Python 3.10+ (Windows, Linux, or macOS)
- Your local dataset file (`.pt` format) or auto-generated MNIST

## Quickstart (Recommended)

When you download your client kit from the Client Portal (`<client-id>-kit.zip`), all scripts are pre-configured:

### On Windows:
```cmd
start.bat
```
*(or double-click `start.bat`)*

### On Linux / macOS:
```bash
bash start.sh
```

The script automatically provisions a `.venv`, installs requirements, downloads sample data (if needed), auto-detects GPU (or falls back to CPU), and connects to the coordinator.

---

## Manual Execution

```bash
pip install -r requirements.txt

python agent.py \
  --coordinator http://<host-ip>:8000 \
  --client-id <your-client-id> \
  --token <your-client-token> \
  --kit-dir . \
  --data-path dataset/mnist.pt
```

## What it does

1. Patches `startup/fed_client.json` with the host/coordinator address.
2. Injects `sitecustomize.py` to ensure Windows path safety for NVFlare subprocess execution.
3. Sends heartbeats to the coordinator every 5 seconds.
4. Waits for jobs and launches federated learning using PyTorch.
5. Raw training data never leaves your computer — only encrypted weight updates are sent back.
