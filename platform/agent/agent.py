"""
NexMesh client agent — NVFlare-based federated learning.

Usage:
    python agent.py \\
        --coordinator http://<host-ip>:8000 \\
        --client-id <your-client-id> \\
        --token <your-client-token> \\
        --kit-dir /path/to/nvflare-kit \\
        --data-path /path/to/mnist.pt \\
        --server-host <host-ip>          # defaults to coordinator host
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

POLL_INTERVAL = 15


def api(coordinator, path, method="GET", token="", **kwargs):
    headers = {"X-Nexmesh-Client-Token": token, "Content-Type": "application/json"}
    r = requests.request(method, f"{coordinator}{path}", headers=headers, timeout=30, **kwargs)
    r.raise_for_status()
    return r.json()


def heartbeat(coordinator, client_id, token):
    return api(coordinator, f"/agent/{client_id}/heartbeat", method="POST", token=token)["status"]


def get_agent_jobs(coordinator, client_id, token):
    r = requests.request(
        "GET", f"{coordinator}/agent/{client_id}/jobs",
        headers={"X-Nexmesh-Client-Token": token}, timeout=30,
    )
    r.raise_for_status()
    return r.json()


def submit_job_result(coordinator, client_id, job_id, status, metrics=None):
    payload = {"status": status, "metrics": metrics or {}}
    r = requests.request(
        "POST", f"{coordinator}/agent/{client_id}/jobs/{job_id}/result",
        headers={"X-Nexmesh-Client-Token": token, "Content-Type": "application/json"},
        json=payload, timeout=30,
    )
    r.raise_for_status()
    return r.json()


def patch_kit(kit_dir: Path, server_host: str) -> None:
    """Rewrite fed_client.json to point at the real server IP/hostname."""
    fed_client = kit_dir / "startup" / "fed_client.json"
    if not fed_client.exists():
        print(f"[agent] WARNING: {fed_client} not found, skipping patch")
        return
    cfg = json.loads(fed_client.read_text())
    for server in cfg.get("servers", []):
        old_target = server.get("service", {}).get("target", "")
        port = old_target.split(":")[-1] if ":" in old_target else "8002"
        server["service"]["target"] = f"{server_host}:{port}"
        old_admin = server.get("admin_server", "")
        if old_admin:
            server["admin_server"] = server_host
    fed_client.write_text(json.dumps(cfg, indent=2))
    print(f"[agent] Patched fed_client.json → server {server_host}")


def wait_for_approval(coordinator, client_id, token):
    print("[agent] Polling for coordinator approval...")
    while True:
        try:
            st = heartbeat(coordinator, client_id, token)
            print(f"[agent] Status: {st}")
            if st in {"APPROVED", "ONLINE", "OFFLINE"}:
                return
            if st not in {"PENDING", "PROVISIONING"}:
                print(f"[agent] Not eligible (status={st}). Exiting.")
                sys.exit(0)
        except requests.ConnectionError:
            print("[agent] Cannot reach coordinator, retrying...")
        time.sleep(POLL_INTERVAL)


def main():
    parser = argparse.ArgumentParser(description="NexMesh NVFlare client agent")
    parser.add_argument("--coordinator", required=True)
    parser.add_argument("--client-id", required=True, dest="client_id")
    parser.add_argument("--token", required=True)
    parser.add_argument("--kit-dir", required=True, dest="kit_dir")
    parser.add_argument("--data-path", required=True, dest="data_path")
    parser.add_argument("--server-host", dest="server_host", default=None,
                        help="NVFlare server host/IP (defaults to coordinator host)")
    parser.add_argument("--epochs", type=int, default=int(os.environ.get("NEXMESH_EPOCHS", "3")))
    parser.add_argument("--batch-size", type=int, default=int(os.environ.get("NEXMESH_BATCH_SIZE", "64")), dest="batch_size")
    args = parser.parse_args()

    kit_dir = Path(args.kit_dir).resolve()
    if not kit_dir.exists():
        print(f"[agent] ERROR: kit directory not found: {kit_dir}")
        sys.exit(1)
    data_path = Path(args.data_path).resolve()
    if not data_path.exists():
        print(f"[agent] ERROR: dataset not found: {data_path}")
        sys.exit(1)

    # derive server host from coordinator URL if not explicitly given
    server_host = args.server_host or urlparse(args.coordinator).hostname
    print(f"[agent] Coordinator: {args.coordinator}  Client: {args.client_id}  Server: {server_host}")

    # patch kit with real server address
    patch_kit(kit_dir, server_host)

    # wait for approval
    wait_for_approval(args.coordinator, args.client_id, args.token)
    print("[agent] Approved. Polling for assigned jobs...")

    # Ensure Windows path safety for NVFlare ProcessJobLauncher
    sitecustomize_path = kit_dir / "sitecustomize.py"
    sitecustomize_code = (
        "import sys, shlex\n"
        "if sys.platform == 'win32':\n"
        "    _orig = shlex.split\n"
        "    def _safe_split(s, comments=False, posix=True):\n"
        "        if posix:\n"
        "            parts = _orig(s, comments=comments, posix=False)\n"
        "            return [p.strip('\"') for p in parts]\n"
        "        return _orig(s, comments=comments, posix=posix)\n"
        "    shlex.split = _safe_split\n"
    )
    sitecustomize_path.write_text(sitecustomize_code)

    startup_script = (kit_dir / "startup" / "sub_start.sh").resolve()
    venv_bin = f"{sys.prefix}/Scripts" if sys.platform == "win32" else f"{sys.prefix}/bin"
    current_path = os.environ.get("PATH", "")
    current_pythonpath = os.environ.get("PYTHONPATH", "")
    env = {
        **os.environ,
        "PATH": f"{venv_bin}{os.pathsep}{current_path}" if venv_bin not in current_path else current_path,
        "PYTHONPATH": f"{kit_dir}{os.pathsep}{current_pythonpath}" if current_pythonpath else str(kit_dir),
        "NEXMESH_DATA_PATH": str(data_path),
        "NEXMESH_EPOCHS": str(args.epochs),
        "NEXMESH_BATCH_SIZE": str(args.batch_size),
    }

    def run_job(job: dict) -> int:
        job_id = job["id"]
        print(f"[agent] Running job {job_id} ...")
        # Direct Python invocation - completely cross-platform on Linux, Windows, and macOS
        cmd = [
            sys.executable, "-u", "-m", "nvflare.private.fed.app.client.client_train",
            "-m", str(kit_dir),
            "-s", "fed_client.json",
            "--set", "secure_train=true",
            f"uid={args.client_id}",
            "org=nvidia",
            "config_folder=config",
        ]
        proc = subprocess.Popen(
            cmd,
            cwd=str(kit_dir),
            env=env,
        )
        try:
            while proc.poll() is None:
                try:
                    st = heartbeat(args.coordinator, args.client_id, args.token)
                    print(f"[agent] Heartbeat: {st}")
                except (requests.ConnectionError, requests.HTTPError) as e:
                    print(f"[agent] Heartbeat error: {e}")
                time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            print("[agent] Interrupted, stopping...")
            proc.terminate()
            proc.wait(timeout=10)
            sys.exit(0)

        rc = proc.returncode
        status = "COMPLETED" if rc == 0 else "FAILED"
        print(f"[agent] NVFlare client for job {job_id} exited with code {rc}")
        try:
            submit_job_result(args.coordinator, args.client_id, job_id, status)
            print(f"[agent] Submitted result for job {job_id}: {status}")
        except Exception as e:
            print(f"[agent] Failed to submit result for job {job_id}: {e}")
        return rc

    try:
        while True:
            try:
                jobs = get_agent_jobs(args.coordinator, args.client_id, args.token)
                pending = [
                    j for j in jobs
                    if j.get("status") not in {"COMPLETED", "FAILED"}
                ]
            except Exception as e:
                print(f"[agent] Failed to fetch jobs: {e}")
                pending = []

            if pending:
                for job in pending:
                    run_job(job)
            else:
                try:
                    st = heartbeat(args.coordinator, args.client_id, args.token)
                    print(f"[agent] Heartbeat: {st} (no assigned jobs)")
                except (requests.ConnectionError, requests.HTTPError) as e:
                    print(f"[agent] Heartbeat error: {e}")
                time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("[agent] Interrupted, stopping...")
        sys.exit(0)


if __name__ == "__main__":
    main()
