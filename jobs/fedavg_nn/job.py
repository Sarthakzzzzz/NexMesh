"""
Submit the fedavg_nn NVFlare job from the admin pod.

Environment variables:
  NEXMESH_CLIENTS      comma-separated NVFlare site names
  NEXMESH_SERVER_NAME  NVFlare server name (default: 192.168.1.43)
  NEXMESH_NUM_ROUNDS   FL rounds (default 5)
  NEXMESH_LOCAL_EPOCHS local epochs per round (default 1)
  NEXMESH_BATCH_SIZE   batch size (default 64)
  NEXMESH_MIN_CLIENTS  minimum clients (default = all)
  NEXMESH_DATA_PATHS   JSON map of site -> data path
  NVFLARE_STARTUP_KIT  path to admin startup kit (default /workspace)
  NVFLARE_USERNAME     admin username (default admin@nvidia.com)
"""
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from nvflare.fuel.flare_api.flare_api import new_secure_session

CLIENT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,62}$")
SCRIPT_DIR = Path(__file__).parent


def main():
    clients = [c.strip() for c in os.getenv("NEXMESH_CLIENTS", "").split(",") if c.strip()]
    if not clients:
        raise ValueError("NEXMESH_CLIENTS must be set")
    if any(not CLIENT_ID_PATTERN.fullmatch(c) for c in clients):
        raise ValueError(f"Invalid client id in NEXMESH_CLIENTS: {clients}")

    server_name = os.getenv("NEXMESH_SERVER_NAME", "192.168.1.43")
    rounds      = int(os.getenv("NEXMESH_NUM_ROUNDS", "5"))
    epochs      = int(os.getenv("NEXMESH_LOCAL_EPOCHS", "1"))
    batch_size  = int(os.getenv("NEXMESH_BATCH_SIZE", "64"))
    min_clients = int(os.getenv("NEXMESH_MIN_CLIENTS", str(len(clients))))
    data_paths  = json.loads(os.getenv("NEXMESH_DATA_PATHS", "{}"))

    with tempfile.TemporaryDirectory(prefix="nexmesh-job-") as tmp:
        job_dir = Path(tmp) / "fedavg_nn"

        # server app — NVFlare requires configs in app/config/
        server_app = job_dir / "server_app"
        server_custom = server_app / "custom"
        server_config = server_app / "config"
        server_custom.mkdir(parents=True)
        server_config.mkdir()
        shutil.copy(SCRIPT_DIR / "server_evaluator.py", server_custom / "server_evaluator.py")
        shutil.copy(SCRIPT_DIR / "app" / "custom" / "train.py", server_custom / "train.py")

        srv_cfg = json.loads((SCRIPT_DIR / "app" / "custom" / "config_fed_server.json").read_text())
        for wf in srv_cfg.get("workflows", []):
            if "scatter_and_gather" in wf.get("id", ""):
                wf["args"]["min_clients"] = min_clients
                wf["args"]["num_rounds"] = rounds
        (server_config / "config_fed_server.json").write_text(json.dumps(srv_cfg, indent=2))

        # per-client apps
        for client in clients:
            client_app = job_dir / f"{client}_app"
            client_custom = client_app / "custom"
            client_config = client_app / "config"
            client_custom.mkdir(parents=True)
            client_config.mkdir()
            shutil.copy(SCRIPT_DIR / "app" / "custom" / "train.py", client_custom / "train.py")

            data_path = data_paths.get(client, f"/data/{client}/mnist.pt")
            wrapper = (
                "#!/bin/sh\n"
                f'export NEXMESH_DATA_PATH="${{NEXMESH_DATA_PATH:-{data_path}}}"\n'
                f'export NEXMESH_EPOCHS="${{NEXMESH_EPOCHS:-{epochs}}}"\n'
                f'export NEXMESH_BATCH_SIZE="${{NEXMESH_BATCH_SIZE:-{batch_size}}}"\n'
                'exec python custom/train.py "$@"\n'
            )
            wrapper_path = client_custom / "run_train.sh"
            wrapper_path.write_text(wrapper)
            wrapper_path.chmod(0o755)

            wrapper_bat = (
                "@echo off\n"
                f'if "%NEXMESH_DATA_PATH%"=="" set "NEXMESH_DATA_PATH={data_path}"\n'
                f'if "%NEXMESH_EPOCHS%"=="" set "NEXMESH_EPOCHS={epochs}"\n'
                f'if "%NEXMESH_BATCH_SIZE%"=="" set "NEXMESH_BATCH_SIZE={batch_size}"\n'
                'python custom\\train.py %*\n'
            )
            (client_custom / "run_train.bat").write_text(wrapper_bat)

            cli_cfg = json.loads((SCRIPT_DIR / "app" / "custom" / "config_fed_client.json").read_text())
            for comp in cli_cfg.get("components", []):
                if comp.get("id") == "executor" and "command" in comp.get("args", {}):
                    comp["args"]["command"] = ["python", "custom/train.py"]
                elif comp.get("id") == "launcher":
                    comp["args"]["script"] = "python custom/train.py"
            for exe in cli_cfg.get("executors", []):
                if isinstance(exe.get("executor"), dict) and "command" in exe["executor"].get("args", {}):
                    exe["executor"]["args"]["command"] = ["python", "custom/train.py"]
            (client_config / "config_fed_client.json").write_text(json.dumps(cli_cfg, indent=2))

        # meta.json — deploy_map maps each app to its target
        deploy_map = {"server_app": ["server"]}
        for client in clients:
            deploy_map[f"{client}_app"] = [client]

        meta = {
            "name": "fedavg_nn",
            "resource_spec": {},
            "deploy_map": deploy_map,
            "min_clients": min_clients,
            "num_rounds": rounds,
        }
        (job_dir / "meta.json").write_text(json.dumps(meta, indent=2))

        startup_kit = os.getenv("NVFLARE_STARTUP_KIT", "/workspace")
        username    = os.getenv("NVFLARE_USERNAME", "admin@nvidia.com")

        print(f"Connecting as {username} from {startup_kit}")
        session = new_secure_session(username=username, startup_kit_location=startup_kit)
        try:
            job_id = session.submit_job(str(job_dir))
            print(f"NEXMESH_JOB_ID={job_id}")
        finally:
            session.close()


if __name__ == "__main__":
    main()
