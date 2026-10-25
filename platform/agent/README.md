# NexMesh Client Agent

Join a NexMesh federation without any NVFlare setup.

## Requirements

- Python 3.10+
- Your local dataset file (`.pt` format)
- Client ID and token from the coordinator (sent by the host)

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
python agent.py \
  --coordinator http://<host-ip>:8000 \
  --client-id <your-client-id> \
  --token <your-client-token> \
  --data-path /path/to/your/dataset.pt
```

## What it does

1. Sends a heartbeat to the coordinator every 15 seconds.
2. Waits until the host approves your client.
3. When a job is assigned, downloads the training package.
4. Trains locally on your dataset — raw data never leaves your machine.
5. Sends only metrics and model results back to the coordinator.

## Custom training package

If the job includes a `train.py`, it must expose:

```python
def train(data_path: str) -> dict:
    # load data, train model, return metrics
    return {"loss": 0.0, "accuracy": 0.0}
```

If no `train.py` is provided, the built-in MNIST trainer is used.
