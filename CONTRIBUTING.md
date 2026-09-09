# Contributing

## Scope

Keep changes focused on the federated-learning workflow, deployment, data
isolation, documentation, or reproducible local setup.

## Before Opening a Change

Run the relevant checks:

```bash
python3 -m py_compile jobs/fedavg_nn/job.py jobs/fedavg_nn/train.py jobs/fedavg_nn/server_evaluator.py workspace/fedlearn/split_mnist.py
python3 - <<'PY'
import yaml
for path in ['kind-config.yaml', 'k8s/nvflare-local.yaml', 'k8s/nvidia-device-plugin.yaml']:
    with open(path) as stream:
        list(yaml.safe_load_all(stream))
print('yaml ok')
PY
git diff --check
```

For deployment changes, also verify that client datasets remain isolated and
that generated certificates, datasets, logs, and model artifacts are ignored.

## Change Guidelines

- Do not commit `.env`, certificates, private keys, datasets, generated kits,
  logs, or model artifacts.
- Keep host-specific paths in `.env`, not tracked source files.
- Preserve the separate client mount paths.
- Document operational changes in `commands.md`.
- Keep README claims limited to verified behavior.
- Do not commit generated runtime state.

Use a concise commit message that describes the change.
