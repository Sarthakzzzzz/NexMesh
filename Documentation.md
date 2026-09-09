# Documentation

This project uses NVIDIA FLARE, PyTorch, Docker, Kubernetes, and Kind for a
three-client MNIST federated-learning proof of concept.

## Workflow

1. Generate deterministic client splits with `workspace/fedlearn/split_mnist.py`.
2. Build the `fedlearn/nvflare:local` image.
3. Create the Kind cluster from the rendered `kind-config.yaml`.
4. Install the NVIDIA device plugin and deploy the NVFlare pods.
5. Verify client data isolation and CUDA availability.
6. Submit `jobs/fedavg_nn/job.py` from the admin pod.

Use [commands.md](commands.md) for the command sequence.

## Data Boundaries

- `site-1` reads only `client_1/mnist.pt`.
- `site-2` reads only `client_2/mnist.pt`.
- `site-3` reads only `client_3/mnist.pt`.
- `server1` reads only the server test split for evaluation.

Raw client data is not sent to the server. Clients send model parameters and
configured metrics through NVFlare.

## Current Scope

The verified experiment uses three clients, five FedAvg rounds, one local epoch
per round, batch size 64, and one time-sliced RTX 5050 shared by the client pods.
Server-side evaluation artifact persistence remains under verification.
