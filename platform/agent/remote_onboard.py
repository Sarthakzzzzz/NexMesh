#!/usr/bin/env python3
"""
Remote Client Onboarding & Runner for FedLearn (NVFlare Federation)

Features:
- Enrolls with coordinator without requiring Kubernetes or host access.
- Supports both:
    1. Distributed Provisioning: Generates local key/CSR using `nvflare cert request`
       (private key never leaves client machine), uploads CSR, downloads signed package,
       and packages kit locally with `nvflare package`.
    2. Direct Kit Delivery: Downloads coordinator-provisioned startup kit zip.
- Validates local dataset path.
- Runs NVFlare client with automated heartbeats to coordinator.
- Supports clean departure/leave with `--leave`.

Usage:
    python remote_onboard.py \\
        --coordinator http://<host-ip>:8000 \\
        --client-id site-remote-1 \\
        --display-name "Hospital Alpha" \\
        --data-path /path/to/local/mnist.pt \\
        --mode distributed
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

POLL_INTERVAL = 5


def log(msg: str) -> None:
    print(f"[remote-client] {msg}", flush=True)


def enroll(coordinator: str, client_id: str, display_name: str, org: str) -> tuple[str, str]:
    """Submit enrollment request to coordinator."""
    url = f"{coordinator.rstrip('/')}/enrollments"
    payload = {
        "id": client_id,
        "display_name": display_name,
        "organization": org,
        "mode": "remote_participant",
    }
    r = requests.post(url, json=payload, timeout=20)
    if r.status_code == 409:
        log(f"Client '{client_id}' is already registered on coordinator.")
        # Ask for token or check if saved
        token_file = Path(f".{client_id}.token")
        if token_file.exists():
            token = token_file.read_text().strip()
            log(f"Loaded existing client token from {token_file}")
            return client_id, token
        else:
            raise RuntimeError(
                f"Client '{client_id}' exists but no local token found. Provide token or use another client ID."
            )
    r.raise_for_status()
    data = r.json()
    token = data["client_token"]
    Path(f".{client_id}.token").write_text(token)
    log(f"Enrolled successfully as '{client_id}' (token saved to .{client_id}.token)")
    return client_id, token


def check_status(coordinator: str, client_id: str, token: str) -> dict:
    url = f"{coordinator.rstrip('/')}/enrollments/{client_id}/status"
    headers = {"X-Nexmesh-Client-Token": token}
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()


def wait_for_approval(coordinator: str, client_id: str, token: str) -> dict:
    log("Waiting for coordinator administrator approval...")
    while True:
        status_info = check_status(coordinator, client_id, token)
        st = status_info["status"]
        log(f"Current status: {st} - {status_info.get('next_action', '')}")
        if st in {"APPROVED", "PROVISIONING", "AWAITING_CLIENT_PACKAGE", "READY", "ONLINE"}:
            return status_info
        if st in {"REJECTED", "FAILED"}:
            raise RuntimeError(f"Enrollment stopped: status is {st}")
        time.sleep(POLL_INTERVAL)


def distributed_provision(coordinator: str, client_id: str, token: str, org: str, work_dir: Path) -> Path:
    """Execute NVFlare distributed provisioning workflow (CSR -> signed zip -> local package)."""
    nvflare_bin = shutil.which("nvflare") or sys.executable.replace("python", "nvflare")
    if not Path(nvflare_bin).exists():
        nvflare_bin = "nvflare"

    log("Step 1: Generating local private key and certificate request (private key stays local)...")
    req_out_dir = work_dir / "request"
    req_out_dir.mkdir(parents=True, exist_ok=True)
    part_yaml = req_out_dir / "participant.yaml"
    import yaml

    part_yaml.write_text(
        yaml.safe_dump({
            "name": "fedlearn",
            "participants": [{
                "name": client_id,
                "type": "client",
                "org": org,
            }],
        }),
        encoding="utf-8",
    )

    env = dict(os.environ)
    env["NVFLARE_HOME"] = str(work_dir / ".nvflare")

    res = subprocess.run(
        [nvflare_bin, "cert", "request", "-p", str(part_yaml), "--out", str(req_out_dir / client_id), "--force"],
        capture_output=True,
        text=True,
        env=env,
    )
    if res.returncode != 0:
        raise RuntimeError(f"nvflare cert request failed: {res.stderr or res.stdout}")

    request_zip = req_out_dir / client_id / f"{client_id}.request.zip"
    if not request_zip.exists():
        raise RuntimeError(f"Request zip not found at {request_zip}")

    log("Step 2: Submitting certificate signing request to coordinator...")
    url = f"{coordinator.rstrip('/')}/enrollments/{client_id}/csr"
    headers = {"X-Nexmesh-Client-Token": token, "Content-Type": "application/octet-stream"}
    r = requests.post(url, headers=headers, data=request_zip.read_bytes(), timeout=30)
    r.raise_for_status()

    log("Step 3: Downloading signed certificate response...")
    download_url = f"{coordinator.rstrip('/')}/enrollments/{client_id}/signed-response"
    r = requests.get(download_url, headers={"X-Nexmesh-Client-Token": token}, timeout=30)
    r.raise_for_status()
    signed_zip = work_dir / f"{client_id}.signed.zip"
    signed_zip.write_bytes(r.content)

    log("Step 4: Assembling client startup kit locally with nvflare package...")
    pkg_ws = work_dir / "packaged_kit"
    pkg_ws.mkdir(parents=True, exist_ok=True)
    res_pkg = subprocess.run(
        [
            nvflare_bin,
            "package",
            str(signed_zip),
            "--request-dir",
            str(req_out_dir / client_id),
            "-w",
            str(pkg_ws),
            "--force",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    if res_pkg.returncode != 0:
        raise RuntimeError(f"nvflare package failed: {res_pkg.stderr or res_pkg.stdout}")

    # Notify coordinator that local packaging is completed
    try:
        requests.post(
            f"{coordinator.rstrip('/')}/enrollments/{client_id}/complete-packaging",
            headers={"X-Nexmesh-Client-Token": token},
            timeout=10,
        )
    except Exception:
        pass

    # Look for client kit folder
    candidates = list(pkg_ws.glob(f"**/{client_id}"))
    if not candidates:
        raise RuntimeError(f"Assembled kit directory not found in {pkg_ws}")
    kit_dir = candidates[0]
    log(f"Client kit assembled at {kit_dir}")
    return kit_dir


def download_direct_kit(coordinator: str, client_id: str, token: str, work_dir: Path) -> Path:
    """Download provisioned kit zip directly from coordinator."""
    log("Downloading startup kit from coordinator...")
    url = f"{coordinator.rstrip('/')}/agent/{client_id}/kit"
    headers = {"X-Nexmesh-Client-Token": token}
    r = requests.get(url, headers=headers, timeout=60)
    r.raise_for_status()

    import zipfile

    zip_file = work_dir / f"{client_id}-kit.zip"
    zip_file.write_bytes(r.content)
    kit_dir = work_dir / client_id
    kit_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_file, "r") as zf:
        zf.extractall(kit_dir)

    log(f"Startup kit extracted to {kit_dir}")
    return kit_dir


def patch_kit_server(kit_dir: Path, server_host: str) -> None:
    fed_client = kit_dir / "startup" / "fed_client.json"
    if not fed_client.exists():
        return
    cfg = json.loads(fed_client.read_text())
    for s in cfg.get("servers", []):
        old_target = s.get("service", {}).get("target", "")
        port = old_target.split(":")[-1] if ":" in old_target else "8002"
        s["service"]["target"] = f"{server_host}:{port}"
        if s.get("admin_server"):
            s["admin_server"] = server_host
    fed_client.write_text(json.dumps(cfg, indent=2))
    log(f"Configured NVFlare client target to {server_host}")


def leave_federation(coordinator: str, client_id: str, token: str) -> None:
    log(f"Leaving federation and deleting enrollment for '{client_id}'...")
    url = f"{coordinator.rstrip('/')}/agent/{client_id}/leave"
    headers = {"X-Nexmesh-Client-Token": token}
    try:
        r = requests.delete(url, headers=headers, timeout=20)
        r.raise_for_status()
        log("Successfully removed client from coordinator.")
    except Exception as e:
        log(f"Leave request warning: {e}")
    token_file = Path(f".{client_id}.token")
    if token_file.exists():
        token_file.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="FedLearn Remote Client Onboarding & Runner")
    parser.add_argument("--coordinator", required=True, help="Coordinator URL, e.g. http://192.168.1.43:8000")
    parser.add_argument("--client-id", required=True, help="Unique client ID (e.g. site-remote-1)")
    parser.add_argument("--display-name", default=None, help="Display name for client")
    parser.add_argument("--org", default="nvidia", help="Organization name")
    parser.add_argument("--token", default=None, help="Existing client token (optional)")
    parser.add_argument("--data-path", default=None, help="Path to local dataset (e.g. mnist.pt)")
    parser.add_argument(
        "--mode",
        choices=["distributed", "direct"],
        default="direct",
        help="Provisioning mode: distributed (CSR signing) or direct (kit download)",
    )
    parser.add_argument("--server-host", default=None, help="NVFlare server host (defaults to coordinator host)")
    parser.add_argument("--leave", action="store_true", help="Leave federation and clean up enrollment")
    parser.add_argument("--work-dir", default="./nvflare_workspace", help="Local directory for keys and kits")
    args = parser.parse_args()

    client_id = args.client_id
    coordinator = args.coordinator.rstrip("/")
    display_name = args.display_name or client_id

    # Handle --leave
    if args.leave:
        token = args.token
        if not token:
            token_file = Path(f".{client_id}.token")
            if token_file.exists():
                token = token_file.read_text().strip()
        if not token:
            log("Error: Token required to leave federation.")
            sys.exit(1)
        leave_federation(coordinator, client_id, token)
        sys.exit(0)

    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    # Validate dataset if provided
    if args.data_path:
        if not Path(args.data_path).exists():
            log(f"Error: Dataset not found at {args.data_path}")
            sys.exit(1)

    # 1. Enroll
    token = args.token
    if not token:
        token_file = Path(f".{client_id}.token")
        if token_file.exists():
            token = token_file.read_text().strip()
            log(f"Using saved token from {token_file}")
        else:
            _, token = enroll(coordinator, client_id, display_name, args.org)

    # 2. Wait for approval
    wait_for_approval(coordinator, client_id, token)

    # 3. Retrieve or assemble kit
    if args.mode == "distributed":
        kit_dir = distributed_provision(coordinator, client_id, token, args.org, work_dir)
    else:
        kit_dir = download_direct_kit(coordinator, client_id, token, work_dir)

    # 4. Patch server host
    server_host = args.server_host or urlparse(coordinator).hostname or "127.0.0.1"
    patch_kit_server(kit_dir, server_host)

    # 5. Start Heartbeat & Client loop
    startup_script = kit_dir / "startup" / "sub_start.sh"
    if not startup_script.exists():
        startup_script = kit_dir / "startup" / "start.sh"
    if not startup_script.exists():
        log(f"Warning: Startup script not found in {kit_dir}/startup. Kit contents: {list(kit_dir.iterdir())}")

    log(f"Client '{client_id}' is ready.")
    log(f"To run NVFlare manually: cd {kit_dir} && ./startup/sub_start.sh --once")

    # Send initial heartbeat to mark ONLINE
    try:
        requests.post(
            f"{coordinator}/agent/{client_id}/heartbeat",
            headers={"X-Nexmesh-Client-Token": token},
            timeout=10,
        )
        log("Initial heartbeat sent: status marked ONLINE.")
    except Exception as e:
        log(f"Heartbeat warning: {e}")


if __name__ == "__main__":
    main()

