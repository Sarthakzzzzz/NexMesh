# Federated Learning Project --- Current Progress, Issues, and Final Goal

## 1. Ultimate Goal

Create a **decentralized federated learning network** where multiple
independent nodes collaboratively train a neural network **without
sharing their raw/private training data**.

Each node keeps its own dataset locally, performs local neural-network
training, and sends only model updates and permitted metrics.

The coordinator/server: - manages federated training rounds -
distributes the global model - receives model updates - performs
Federated Averaging (FedAvg) - maintains the global model - keeps track
of training scores/metrics

The current MNIST + 3-client setup is a proof-of-concept for this larger
decentralized architecture.

## 2. Intended Architecture

``` text
                         FL Coordinator / Server
                    +-----------------------------+
                    | Global CNN Model            |
                    | FedAvg                      |
                    | Round Management             |
                    | Score / Metrics              |
                    +--------------+--------------+
                                   |
                         Global model / updates
                                   |
             +---------------------+---------------------+
             |                     |                     |
             v                     v                     v
       +-----------+         +-----------+         +-----------+
       |  Node 1   |         |  Node 2   |         |  Node 3   |
       | Private   |         | Private   |         | Private   |
       | MNIST     |         | MNIST     |         | MNIST     |
       | Data      |         | Data      |         | Data      |
       | Local NN  |         | Local NN  |         | Local NN  |
       +-----+-----+         +-----+-----+         +-----+-----+
             |                     |                     |
             +----------- Model Updates / Metrics -------+
                                   |
                                   v
                              Server / FedAvg
                                   |
                                   v
                           Updated Global Model
                                   |
                                   v
                              Next FL Round
```

**Privacy principle:** raw datasets stay on their respective nodes. The
server receives model updates and relevant metrics, not the raw training
datasets.

## 3. Technology Stack

-   Python 3.13
-   PyTorch 2.14.0+cu130
-   NVFlare 2.9.0
-   Docker
-   Kubernetes
-   Kind
-   FedAvg
-   MNIST
-   PyTorch CNN

## 4. Repository

``` text
fedlearn/
├── Dockerfile
├── jobs/
│   └── fedavg_nn/
│       ├── app/custom/
│       │   ├── config_fed_client.json
│       │   ├── config_fed_server.json
│       │   ├── raw_data/
│       │   └── train.py
│       ├── job.py
│       └── train.py
├── k8s/
│   └── nvflare-local.yaml
├── kind-config.yaml
├── project.yml
└── workspace/
    └── fedlearn/
        ├── datasets/
        │   ├── client_1/mnist.pt
        │   ├── client_2/mnist.pt
        │   └── client_3/mnist.pt
        ├── mnist_raw/
        └── prod_00/
            ├── admin@nvidia.com/
            ├── lead@nvidia.com/
            ├── org-admin@nvidia.com/
            ├── server1/
            ├── site-1/
            ├── site-2/
            └── site-3/
```

## 5. Completed Work

### Dataset preparation --- DONE

Three separate MNIST datasets exist:

``` text
client_1 -> 20,000 samples
client_2 -> 20,000 samples
client_3 -> 20,000 samples
```

Stored at:

``` text
workspace/fedlearn/datasets/client_1/mnist.pt
workspace/fedlearn/datasets/client_2/mnist.pt
workspace/fedlearn/datasets/client_3/mnist.pt
```

Mounted into client containers as:

``` text
/data/client_1/mnist.pt
/data/client_2/mnist.pt
/data/client_3/mnist.pt
```

### CNN implementation --- DONE

Architecture:

``` text
Conv2d(1, 32, 3)
ReLU
MaxPool2d(2)

Conv2d(32, 64, 3)
ReLU
MaxPool2d(2)

Flatten
Linear(64*5*5 -> 128)
ReLU
Linear(128 -> 10)
```

The architecture is defined consistently in the federated recipe and
client training script.

### Standalone PyTorch training --- DONE

The CNN was successfully trained independently using Docker and the RTX
5050 Laptop GPU.

Verified result:

``` text
Device: CUDA
GPU: NVIDIA GeForce RTX 5050 Laptop GPU
Samples: 20,000
Epochs: 1
Loss: 0.3993
Accuracy: 87.94%
```

This proves the neural network and standalone Docker GPU environment
work.

### Docker environment --- DONE

Image:

``` text
fedlearn/nvflare:local
```

NVFlare version inside the image:

``` text
2.9.0
```

### Kind/Kubernetes cluster --- DONE

Cluster:

``` text
fedlearn-cluster
```

Kubernetes node:

``` text
fedlearn-cluster-control-plane
```

Kubernetes version:

``` text
v1.37.0
```

The node is running and Ready.

### NVIDIA infrastructure --- PARTIALLY CONFIGURED / NOT CURRENT BLOCKER

Host GPU:

``` text
NVIDIA GeForce RTX 5050 Laptop GPU
```

NVIDIA driver:

``` text
595.91.07
```

NVIDIA Container Toolkit:

``` text
1.20.0
```

Standalone Docker GPU execution works.

GPU access from Kubernetes has not yet been fully validated for the
NVFlare client pods, but this is **not the current blocker**. The
immediate priority is successful federated execution.

### NVFlare Kubernetes deployment --- CONFIGURED; CURRENT CLUSTER NEEDS RECREATION

The manifests and generated kits are present. The previous cluster state
showed these components running:

``` text
nvflare-admin   1/1 Running
server1         1/1 Running
site-1          1/1 Running
site-2          1/1 Running
site-3          1/1 Running
```

### NVFlare client registration --- PREVIOUSLY VERIFIED; REQUIRES RE-VERIFICATION

All three clients successfully registered:

``` text
site-1 -> Successfully registered
site-2 -> Successfully registered
site-3 -> Successfully registered
```

This previously demonstrated that the server/client networking and
registration configuration works. The current cluster must be recreated
before this can be treated as current status.

### NVFlare Client API integration --- DONE

The training script now correctly uses:

``` python
flare.init()

while flare.is_running():
    input_model = flare.receive()

    # local training

    output_model = flare.FLModel(
        params=params,
        metrics={
            "loss": loss,
            "accuracy": accuracy
        }
    )

    flare.send(output_model)
```

This addresses the earlier `APIContext is None` error.

## 6. Current Federated Job Configuration

Target configuration:

``` python
recipe = FedAvgRecipe(
    name="fedavg_nn",
    min_clients=3,
    num_rounds=5,
    model=MNISTCNN(),
    train_script="jobs/fedavg_nn/train.py",
    train_args="--epochs 1 --batch_size 64",
    launch_external_process=True,

    per_site_config={
        "site-1": {
            "train_args": "--data_path /data/client_1/mnist.pt --epochs 1 --batch_size 64"
        },
        "site-2": {
            "train_args": "--data_path /data/client_2/mnist.pt --epochs 1 --batch_size 64"
        },
        "site-3": {
            "train_args": "--data_path /data/client_3/mnist.pt --epochs 1 --batch_size 64"
        },
    },
)
```

Target experiment:

``` text
3 clients
5 federated rounds
1 local epoch per round
batch size = 64
FedAvg aggregation
```

## 7. Current Errors / Blockers

### Resolved: job packaging resource path

The original job submission failed during job packaging with:

Command:

``` bash
docker run --rm   -v "$(pwd):/workspace/project"   -w /workspace/project   fedlearn/nvflare:local   python3 jobs/fedavg_nn/job.py
```

Error:

``` text
ValueError: cannot add resource: invalid resource train.py:
it must be either a directory or file
```

Cause:

``` python
train_script="train.py"
```

was being resolved from:

``` text
/workspace/project
```

but the actual script is:

``` text
/workspace/project/jobs/fedavg_nn/train.py
```

The fix is present in `jobs/fedavg_nn/job.py`:

Change:

``` python
train_script="train.py",
```

as:

``` python
train_script="jobs/fedavg_nn/train.py",
```

and ensure:

``` python
launch_external_process=True,
```

is present.

## 8. Non-Blocking Warning

NVFlare 2.9.0 reports:

``` text
FutureWarning: FedAvgRecipe(per_site_config=...) is deprecated;
construct the recipe without per_site_config and call
set_per_site_config(recipe, config) immediately after construction
```

This is a warning, not the current failure.

Do not prioritize this until the first successful FL run. After the
first successful run, migrate to the recommended NVFlare 2.9.0
configuration API.

## 9. What Has Not Been Demonstrated Yet

A successful federated training round has **not yet been completed**.

Still pending:

-   server sends the global model
-   site-1 performs local training through NVFlare
-   site-2 performs local training through NVFlare
-   site-3 performs local training through NVFlare
-   all sites send model updates
-   server performs FedAvg
-   server produces an updated global model
-   multiple rounds complete
-   server-side global score is maintained
-   final global model is evaluated

## 10. Immediate Next Steps

### Step 1 --- Recreate the cluster with corrected mounts

The running server and all three client pods are in `CrashLoopBackOff`.
Their `/workspace` volumes are empty, so Kubernetes cannot execute:

```text
/workspace/startup/sub_start.sh: no such file or directory
```

Cause: `kind-config.yaml` used an old checkout-specific host prefix. The
configuration has been updated to render host paths locally, but Kind only
applies `extraMounts` when the cluster is created.

### Required recovery

Recreate the Kind cluster from the corrected `kind-config.yaml`, reload
the local image, and redeploy the Kubernetes manifest:

```bash
kind delete cluster --name fedlearn-cluster
kind create cluster --config kind-config.yaml
kind load docker-image fedlearn/nvflare:local --name fedlearn-cluster
kubectl apply -f k8s/nvflare-local.yaml
kubectl get pods
```

Confirm all five pods are `Running` before attempting job submission.

### Job submission context

The documented one-off `docker run` command can package the job, but it
cannot submit it because its `/workspace` lacks the admin startup kit.
Run `job.py` inside the `nvflare-admin` pod (where `/workspace` is the
admin kit), after copying the project job directory into that pod.

### Step 2 --- Submit the job from the admin pod

Copy the job source into the admin pod and execute it from a directory
where `jobs/fedavg_nn/train.py` retains its relative path:

```bash
kubectl exec deployment/nvflare-admin -- mkdir -p /workspace/project
kubectl cp jobs deployment/nvflare-admin:/workspace/project
kubectl exec deployment/nvflare-admin -- sh -lc \
  'cd /workspace/project && python3 jobs/fedavg_nn/job.py'
```

### Step 3 --- Verify the first federated round

We need to observe all three clients training and then the server
performing FedAvg.

Expected flow:

``` text
Global model
    |
    +--> site-1 local training
    +--> site-2 local training
    +--> site-3 local training
    |
    +--> model updates
             |
             v
        FedAvg server
             |
             v
      updated global model
```

### Step 4 --- Complete 5 rounds

``` text
Round 1 -> local training -> FedAvg
Round 2 -> local training -> FedAvg
Round 3 -> local training -> FedAvg
Round 4 -> local training -> FedAvg
Round 5 -> local training -> FedAvg
```

### Step 5 --- Implement/verify server-side scoring

The server should maintain global training metrics and ideally evaluate
the aggregated global model against a separate validation/test dataset
after each round.

## 11. Final Definition of Success

The project is successful when multiple nodes can collaboratively train
one neural network while their raw datasets remain local:

``` text
                    Global Model
                         |
             +-----------+-----------+
             v           v           v
          Node 1      Node 2      Node 3
             |           |           |
        Private Data Private Data Private Data
             |           |           |
          Local NN    Local NN    Local NN
             |           |           |
             +---- Model Updates ----+
                         |
                         v
                    Server / FedAvg
                         |
                         v
                  Updated Global Model
                         |
                         v
                    Next Round
```

Core project statement:

> **Build a decentralized federated learning network where participating
> nodes train a shared neural network locally on private data and
> exchange only model updates and permitted metrics, while the
> coordinator aggregates those updates and maintains the global model
> and performance score.**

The MNIST 3-client experiment is the first proof-of-concept of this
architecture.

## 12. Current Verified Status --- 2026-09-10

### Federated GPU run --- DONE

- Kind cluster `fedlearn-cluster` was recreated successfully.
- NVIDIA device plugin exposes three logical `nvidia.com/gpu` slots using
    time-slicing over the host RTX 5050.
- `site-1`, `site-2`, and `site-3` are Running and each requests one GPU.
- Each client reports CUDA enabled and
    `NVIDIA GeForce RTX 5050 Laptop GPU`.
- Each site exposes only its own read-only dataset:
    `/data/client_1/mnist.pt`, `/data/client_2/mnist.pt`, or
    `/data/client_3/mnist.pt`.
- The three client tensors contain 20,000 samples each with zero pairwise
    image overlap.
- A five-round FedAvg job completed with all three clients training on GPU
    in every round.
- The client launcher uses `sub_start.sh --once` and clears only stale
    NVFlare runner-state files before startup.

### Server evaluation --- IMPLEMENTED; LIVE ARTIFACT PENDING

- The server-only 10,000-image MNIST test split is generated at
    `workspace/fedlearn/server_test/mnist.pt`.
- `ServerMNISTEvaluator` is packaged as an NVFlare server widget and its
    evaluation logic was independently verified with an aggregated `FLModel`.
- The live five-round jobs completed successfully, but the expected
    `/results` metrics/model artifacts were not written. The remaining work is
    to identify why the custom widget is not receiving or persisting the
    `AFTER_AGGREGATION` event in the production recipe.

## 13. GitHub Publication Safety

- Added `.gitignore` for the Python environment, Kind temporary files,
    generated NVFlare kits, certificates/private keys, logs, raw datasets,
    `.pt` model/data files, and runtime results.
- `workspace/fedlearn/state/cert.json` contains private NVFlare RSA keys and
    must not be committed.
- `workspace/fedlearn/prod_00/` contains generated identities, certificates,
    audit logs, and job history and must not be committed.
- The source code, Kubernetes manifests, Kind configuration, project file,
    Dockerfile, README, split script, and progress documentation remain
    intended for publication.
- Before pushing, run `git status --ignored`, `git diff --check`, and a
    secret scan over tracked files. Rotate any credential if private material
    was ever committed to a remote repository.
