# Ecosystem Overview

## Components

- **NVIDIA FLARE** coordinates jobs, rounds, client communication, and FedAvg.
- **PyTorch** defines and trains the MNIST CNN.
- **Docker** packages the Python and NVFlare runtime.
- **Kubernetes** runs the server, admin, and three client pods.
- **Kind** provides the local Kubernetes cluster.
- **NVIDIA device plugin** exposes three time-sliced logical GPU slots.
- **MNIST** supplies the client and server test data.

## Topology

```text
server1
  |
  +-- site-1 -- client_1 data
  +-- site-2 -- client_2 data
  +-- site-3 -- client_3 data
```

Each client trains locally. The server aggregates model updates. The server
test split is evaluation-only and is not mounted into client pods.

## Repository Boundaries

- `jobs/` contains federated job and training code.
- `k8s/` contains Kubernetes resources.
- `kind-config.yaml` is a local-path template for Kind.
- `workspace/fedlearn/split_mnist.py` creates local data artifacts.
- `commands.md` contains operational commands.
