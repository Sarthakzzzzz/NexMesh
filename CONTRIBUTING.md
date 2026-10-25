# Contributing to NexMesh

Thank you for your interest in contributing to NexMesh! 

NexMesh is a decentralized federated learning platform engineered with strict privacy boundaries: raw training datasets remain on participant machines, and only model weight updates and loss/accuracy metrics are transmitted over secure mutual TLS.

---

## 1. Guiding Principles & Scope

When submitting changes, ensure adherence to these core tenets:

1. **Strict Data Boundary**: Raw training data must **never** be mounted on the central server pod or transmitted across the network. Central evaluation must only run on server-side test partitions (`/data/server_test`).
2. **Cross-Platform Portability**: Remote client components must run natively on **Windows** (without requiring WSL or Git Bash) as well as **Linux** and **macOS**.
   - Scripts that run on participant machines must provide both `start.bat` and `start.sh`.
   - Python code must handle platform-specific paths (e.g., preserving backslashes on Windows, using `os.pathsep` or `Path`).
3. **Heterogeneous Hardware Acceleration**: Client training scripts must dynamically detect NVIDIA CUDA GPUs and fall back to CPU automatically without code modifications.
4. **Network Agnosticism**: Network endpoints must bind to `0.0.0.0` or dynamically resolve remote host addresses to support Tailscale mesh networks, private LANs, and VPNs.

---

## 2. Local Development & Verification

Before submitting changes, run the validation checklist:

### A. Python Syntax & Compilation Check
```bash
# Verify all platform and job Python code compiles cleanly
python3 -m py_compile \
  jobs/fedavg_nn/job.py \
  jobs/fedavg_nn/train.py \
  jobs/fedavg_nn/server_evaluator.py \
  platform/agent/agent.py \
  platform/backend/main.py
```

### B. Kubernetes & Kind Manifest Validation
```bash
python3 - <<'PY'
import yaml
for path in ['kind-config.yaml', 'k8s/nvflare-server.yaml', 'k8s/nvflare-local.yaml']:
    with open(path) as stream:
        list(yaml.safe_load_all(stream))
print('All Kubernetes and Kind YAML manifests are valid.')
PY
```

### C. Run Backend & Integration Test Suite
```bash
# Run integration tests (validates client enrollment, approval, kit packaging, and API connectivity)
./commands/6_test_workflow.sh

# Or run pytest unit tests directly
pytest platform/backend/services
```

### D. Frontend Build Verification
```bash
# Host Dashboard UI
cd platform/frontend && npm run build && cd ../..

# Participant Client Portal UI
cd platform/client-frontend && npm run build && cd ../..
```

---

## 3. Privacy, Security & Git Hygiene

We enforce strict privacy controls on repository commits:

- **Never Commit Secrets or Local Environment Files**:
  - Do not commit `.env`, `.env.*` (only generic `.env.example` is tracked).
  - Do not commit private keys (`*.key`), certificates (`*.pem`, `*.crt`), or the root CA in `workspace/fedlearn/state/`.
  - Do not commit SQLite database files (`platform/nexmesh.db*`).
- **Never Commit Participant Kits or Datasets**:
  - Exclude all generated kit archives (`*.zip`, `*-kit/`, `client-kit/`, `my-client-kit*/`).
  - Exclude dataset directories (`dataset/`, `datasets/`, `mnist_raw/`) and model weights (`*.pt`, `*.pth`, `*.ckpt`).
- **No Hardcoded Personal IPs or Paths**:
  - Never commit real Tailscale IPs (`100.x.y.z`), LAN IPs, or personal user home directories (`/home/<user>/...` or `C:\Users\<user>\...`).
  - Always use placeholders (e.g., `<HOST_IP>`, `<TAILSCALE_IP>`, `/path/to/fedlearn`).
- **Audit Before Committing**:
  ```bash
  # Check for unstaged leaks or unintended files
  git status
  git diff --check
  ```

---

## 4. Commit Message Guidelines

Use clear, structured commit messages following the [Conventional Commits](https://www.conventionalcommits.org/) convention:

- `feat:` for new capabilities (e.g., `feat: Add Windows 1-click startup script`)
- `fix:` for bug fixes (e.g., `fix: Correct NVFlare executor schema in config_fed_client.json`)
- `docs:` for documentation updates (e.g., `docs: Update architecture diagram and benchmark results`)
- `refactor:` for code restructurings without behavior changes
- `test:` for additions or fixes to the test suite

### Recommended Commit Format:
```bash
git commit \
  -m "type(scope): concise title in imperative mood" \
  -m "Detailed paragraph or bullet points explaining what was changed and why."
```
