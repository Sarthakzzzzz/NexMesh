# FedLearn Commands

Run these commands from the repository root. The Kind config is a template and
must be rendered locally because Kind requires absolute host paths:

```bash
cd /path/to/fedlearn
set -a
. .env
set +a
mkdir -p .kind_tmp
envsubst '${FEDLEARN_ROOT}' < kind-config.yaml > .kind_tmp/kind-config.yaml
```

## Local environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install nvflare torch torchvision numpy pandas pyyaml
```

## Generate isolated datasets

This creates three seeded, non-overlapping client shards and the separate
server-only MNIST test split. The generated `.pt` files are ignored by Git.

```bash
cd workspace/fedlearn
../../.venv/bin/python split_mnist.py
cd ../..
find workspace/fedlearn/datasets -maxdepth 2 -type f -ls
stat workspace/fedlearn/server_test/mnist.pt
```

## Build the local image

```bash
docker build -t "$NVFLARE_IMAGE" .
```

## Recreate Kind with GPU support

The Kind configuration mounts the host NVIDIA runtime, driver libraries,
separate client datasets, the server test set, and generated NVFlare kits.

```bash
kind delete cluster --name "$KIND_CLUSTER_NAME"
TMPDIR="$KIND_TMPDIR" \
  kind create cluster --config .kind_tmp/kind-config.yaml
TMPDIR="$KIND_TMPDIR" \
  kind load docker-image "$NVFLARE_IMAGE" --name "$KIND_CLUSTER_NAME"
```

Install the project-scoped NVIDIA runtime class and time-sliced device plugin:

```bash
kubectl apply -f k8s/nvidia-device-plugin.yaml
kubectl rollout status daemonset/nvidia-device-plugin-daemonset \
  -n kube-system --timeout=120s
```

Deploy NVFlare:

```bash
kubectl apply -f k8s/nvflare-local.yaml
kubectl get pods -o wide
```

## Verify GPU and data isolation

```bash
kubectl get node -o custom-columns=NAME:.metadata.name,ALLOCATABLE_GPU:.status.allocatable.nvidia\\.com/gpu
kubectl get pods -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,GPU:.spec.containers[0].resources.limits.nvidia\\.com/gpu
```

Expected GPU capacity is `3`, with one GPU request on each client pod.

```bash
for site in site-1 site-2 site-3; do
  kubectl exec deployment/$site -- python3 -c \
    'import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))'
done

kubectl exec deployment/site-1 -- find /data -type f
kubectl exec deployment/site-2 -- find /data -type f
kubectl exec deployment/site-3 -- find /data -type f
kubectl exec deployment/server1 -- find /data/server_test -type f
```

Each site should expose only its matching `client_N/mnist.pt`. The server
should expose only `server_test/mnist.pt` from the training-data mounts.

Verify one NVFlare client process per site:

```bash
for site in site-1 site-2 site-3; do
  echo "--- $site"
  kubectl exec deployment/$site -- sh -c \
    'for f in /proc/[0-9]*/cmdline; do tr "\\000" " " < "$f" 2>/dev/null; echo; done' \
    | grep 'nvflare.private.fed.app.client.client_train'
done
```

## Submit the federated job

The job must be submitted from the admin pod because that pod has the admin
startup kit. Resolve its generated pod name rather than assuming a pod named
`nvflare-admin` exists.

```bash
ADMIN_POD=$(kubectl get pods -l app=nvflare-admin \
  -o jsonpath='{.items[0].metadata.name}')
kubectl exec "$ADMIN_POD" -- rm -rf /workspace/project
kubectl exec "$ADMIN_POD" -- mkdir -p /workspace/project
kubectl cp jobs "$ADMIN_POD":/workspace/project
kubectl exec "$ADMIN_POD" -- sh -lc \
  'cd /workspace/project && python3 jobs/fedavg_nn/job.py'
```

The recipe runs five rounds, requires all three clients, uses one local epoch,
uses batch size 64, and passes each site its own dataset path.

## Monitor training

```bash
kubectl logs deployment/server1 -f
kubectl logs deployment/site-1 -f
kubectl logs deployment/site-2 -f
kubectl logs deployment/site-3 -f
```

Inspect completed client round output:

```bash
for site in site-1 site-2 site-3; do
  echo "--- $site"
  kubectl logs deployment/$site --since=30m \
    | grep -E 'Device:|GPU:|site=.*round='
done
```

## Server artifacts

The intended server output directory is `/results`, backed by the host
directory `workspace/fedlearn/results`:

```bash
SERVER_POD=$(kubectl get pods -l app=server1 \
  -o jsonpath='{.items[0].metadata.name}')
kubectl exec "$SERVER_POD" -- find /results -maxdepth 1 -type f -ls
kubectl exec "$SERVER_POD" -- cat /results/server_test_metrics.jsonl
kubectl exec "$SERVER_POD" -- cat /results/summary.json
```

Expected artifacts are:

- `server_test_metrics.jsonl`: one JSON record per aggregation
- `summary.json`: all round records
- `final_global_model.pt`: final aggregated model

The client GPU training path is verified. If these files are absent, inspect
the server job log and evaluator registration before treating the run as fully
complete.

## Troubleshooting

```bash
kubectl get pods -A
kubectl describe pod <pod-name>
kubectl get events --sort-by=.lastTimestamp
kubectl logs -n kube-system -l name=nvidia-device-plugin-ds --tail=100
```

Check the host GPU prerequisites:

```bash
nvidia-smi
nvidia-container-cli --load-kmods info
```

## Cleanup

```bash
kind delete cluster --name "$KIND_CLUSTER_NAME"
```

Do not delete `workspace/fedlearn/state` or `workspace/fedlearn/prod_00` by
hand unless you intend to regenerate the NVFlare project and certificates.
They are ignored because they contain private/generated runtime state.

## GitHub publication

```bash
git status --ignored
git check-ignore -v workspace/fedlearn/state/cert.json
git check-ignore -v workspace/fedlearn/datasets/client_1/mnist.pt
git diff --check
git add .
git status
git commit -m "Document GPU-backed federated MNIST workflow"
git remote -v
git push -u origin main
```

Never force-add ignored certificates, datasets, model files, or generated
NVFlare kits. If private material was previously pushed, rotate the affected
credentials before publishing the repository.