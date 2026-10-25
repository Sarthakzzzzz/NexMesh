import hmac
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except ImportError:
    pass

try:
    from .database import connect, initialize
    from .services.provisioning_service import NVFlareProvisioningService, ProvisioningError
except ImportError:
    from database import connect, initialize
    from services.provisioning_service import NVFlareProvisioningService, ProvisioningError


app = FastAPI(title="NexMesh Coordinator", version="0.2.0")
cors_origins = [origin.strip() for origin in os.getenv("NEXMESH_CORS_ORIGINS", "*").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if "*" in cors_origins else cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
bearer = HTTPBearer(auto_error=False)
HOST_TOKEN = os.getenv("NEXMESH_HOST_TOKEN") or os.getenv("VITE_HOST_TOKEN", "changeme")
AGENT_TOKEN = os.getenv("NEXMESH_AGENT_TOKEN", "agent-test")

AGENT_DIR = os.path.join(os.path.dirname(__file__), "..", "agent")
DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), "..", "host-dashboard")
PORTAL_DIR = os.path.join(os.path.dirname(__file__), "..", "client-frontend", "dist")
ASSETS_DIR = os.path.join(PORTAL_DIR, "assets")

if os.path.isdir(AGENT_DIR):
    app.mount("/static", StaticFiles(directory=AGENT_DIR), name="static")

if os.path.isdir(PORTAL_DIR):
    app.mount("/portal", StaticFiles(directory=PORTAL_DIR, html=True), name="portal")
if os.path.isdir(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="portal_assets")


@app.get("/dashboard", include_in_schema=False)
def host_dashboard() -> FileResponse:
    return FileResponse(os.path.join(DASHBOARD_DIR, "index.html"))


ClientMode = Literal["managed_kubernetes", "remote_participant"]


class ClientCreate(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{2,62}$")
    display_name: str = Field(min_length=1, max_length=120)
    organization: str = Field(default="nvidia", min_length=1, max_length=120)
    mode: ClientMode = "remote_participant"
    dataset_ref: str | None = None
    endpoint: str | None = None
    capabilities: dict[str, Any] = Field(default_factory=dict)


class ClientUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    organization: str | None = Field(default=None, min_length=1, max_length=120)
    dataset_ref: str | None = None
    endpoint: str | None = None
    capabilities: dict[str, Any] | None = None


class ConnectionRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    organization: str = Field(default="nvidia", min_length=1, max_length=120)
    endpoint: str | None = None
    capabilities: dict[str, Any] = Field(default_factory=dict)


class EnrollmentCreate(BaseModel):
    id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]{2,62}$")
    display_name: str = Field(min_length=1, max_length=120)
    organization: str = Field(default="nvidia", min_length=1, max_length=120)
    mode: ClientMode = "remote_participant"
    endpoint: str | None = None
    capabilities: dict[str, Any] = Field(default_factory=dict)


class JobCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    requirements: str = Field(min_length=1, max_length=10000)
    package_url: str | None = None
    participants: list[str] = Field(min_length=1)


class JobResult(BaseModel):
    status: Literal["COMPLETED", "FAILED"]
    metrics: dict[str, Any] = Field(default_factory=dict)
    result_ref: str | None = None


class NVFlareJobSubmit(BaseModel):
    participants: list[str] = Field(min_length=1)
    data_paths: dict[str, str] = Field(default_factory=dict)
    num_rounds: int = Field(default=5, ge=1)
    local_epochs: int = Field(default=1, ge=1)
    batch_size: int = Field(default=64, ge=1)
    min_clients: int | None = None


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_provisioning_service() -> NVFlareProvisioningService:
    repo_root = Path(__file__).resolve().parent.parent.parent
    project_file = os.getenv("NEXMESH_PROJECT_FILE", str(repo_root / "project.yml"))
    workspace = os.getenv("NEXMESH_WORKSPACE", str(repo_root / "workspace" / "fedlearn"))
    return NVFlareProvisioningService(project_file=project_file, workspace=workspace)


def require_host(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
    if not HOST_TOKEN or credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="host authentication required")
    if not hmac.compare_digest(credentials.credentials, HOST_TOKEN):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid host token")


def require_agent(x_nexmesh_agent_token: str | None = Header(default=None)) -> None:
    if not AGENT_TOKEN or not x_nexmesh_agent_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="agent authentication required")
    if not hmac.compare_digest(x_nexmesh_agent_token, AGENT_TOKEN):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid agent token")


def serialize(row: Any) -> dict[str, Any]:
    result = dict(row)
    if "capabilities_json" in result:
        result["capabilities"] = json.loads(result.pop("capabilities_json"))
    result.pop("agent_token", None)
    return result


def get_client(client_id: str) -> dict[str, Any]:
    with connect() as database:
        row = database.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="client not found")
    return serialize(row)


def require_client(client_id: str, x_nexmesh_client_token: str | None) -> dict[str, Any]:
    with connect() as database:
        row = database.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="client not found")
    if not x_nexmesh_client_token or not row["agent_token"] or not hmac.compare_digest(x_nexmesh_client_token, row["agent_token"]):
        raise HTTPException(status_code=401, detail="client authentication required")
    return serialize(row)


def _execute_client_provisioning(client_id: str, organization: str = "nvidia") -> Path:
    svc = _get_provisioning_service()
    try:
        kit_path = svc.add_client(client_id, organization)
        with connect() as database:
            database.execute(
                "UPDATE clients SET status = 'READY', nvflare_identity = ?, error_detail = NULL, updated_at = ? WHERE id = ?",
                (str(kit_path), now(), client_id),
            )
        return kit_path
    except Exception as error:
        detail = str(error)
        with connect() as database:
            database.execute(
                "UPDATE clients SET status = 'FAILED', error_detail = ?, updated_at = ? WHERE id = ?",
                (detail, now(), client_id),
            )
        raise HTTPException(status_code=500, detail=f"Provisioning failed: {detail}")


def _determine_next_action(client: dict[str, Any]) -> str:
    st = client.get("status")
    if st == "PENDING":
        return "Waiting for administrator approval on coordinator"
    if st in {"APPROVED", "PROVISIONING"}:
        return "Coordinator approved; kit provisioning or CSR submission in progress"
    if st == "AWAITING_CLIENT_PACKAGE":
        return "Signed certificate response ready; download and package client kit"
    if st == "READY":
        return "Startup kit is ready; start NVFlare client"
    if st == "ONLINE":
        return "NVFlare client is running and connected"
    if st == "OFFLINE":
        return "NVFlare client is offline; restart client agent"
    if st == "REJECTED":
        return "Enrollment request was rejected by coordinator"
    if st == "FAILED":
        return f"Provisioning failed: {client.get('error_detail') or 'error'}"
    if st == "DISABLED":
        return "Client is disabled by administrator"
    return "No action required"


@app.on_event("startup")
def startup() -> None:
    initialize()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Enrollment & Client Registration Endpoints
# ---------------------------------------------------------------------------

@app.post("/client-requests", status_code=201)
def request_connection(request: ConnectionRequest) -> dict[str, Any]:
    """Client self-registration from client portal (creates PENDING client, no kit yet)."""
    client_id = f"remote-{uuid.uuid4().hex[:10]}"
    agent_token = secrets.token_urlsafe(32)
    timestamp = now()
    with connect() as database:
        database.execute(
            """INSERT INTO clients
            (id, display_name, organization, mode, status, endpoint, capabilities_json,
             agent_token, created_at, updated_at)
            VALUES (?, ?, ?, 'remote_participant', 'PENDING', ?, ?, ?, ?, ?)""",
            (client_id, request.display_name, request.organization, request.endpoint, json.dumps(request.capabilities), agent_token, timestamp, timestamp),
        )
    return {"client_id": client_id, "client_token": agent_token, "status": "PENDING"}


@app.post("/enrollments", status_code=201)
def create_enrollment(request: EnrollmentCreate) -> dict[str, Any]:
    """Formal enrollment creation endpoint conforming to prompt specification."""
    client_id = request.id or f"remote-{uuid.uuid4().hex[:10]}"
    agent_token = secrets.token_urlsafe(32)
    timestamp = now()
    with connect() as database:
        try:
            database.execute(
                """INSERT INTO clients
                (id, display_name, organization, mode, status, endpoint, capabilities_json,
                 agent_token, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'PENDING', ?, ?, ?, ?, ?)""",
                (client_id, request.display_name, request.organization, request.mode, request.endpoint, json.dumps(request.capabilities), agent_token, timestamp, timestamp),
            )
        except Exception as error:
            if "UNIQUE constraint failed" in str(error):
                raise HTTPException(status_code=409, detail=f"Client id '{client_id}' already enrolled") from error
            raise

    client = get_client(client_id)
    return {
        "id": client_id,
        "client_token": agent_token,
        "status": "PENDING",
        "next_action": _determine_next_action(client),
        "client": client,
    }


@app.get("/enrollments/{client_id}/status")
def enrollment_status(client_id: str, x_nexmesh_client_token: str | None = Header(default=None)) -> dict[str, Any]:
    client = get_client(client_id)
    # Check client token if provided
    if x_nexmesh_client_token:
        require_client(client_id, x_nexmesh_client_token)
    return {
        "id": client_id,
        "status": client["status"],
        "display_name": client.get("display_name"),
        "mode": client.get("mode"),
        "organization": client.get("organization"),
        "kit_ready": bool(client.get("nvflare_identity")),
        "signed_package_ready": bool(client.get("signed_package_path")),
        "next_action": _determine_next_action(client),
        "last_heartbeat": client.get("last_heartbeat"),
        "updated_at": client.get("updated_at"),
    }


@app.post("/enrollments/{client_id}/approve", dependencies=[Depends(require_host)])
def approve_enrollment(client_id: str) -> dict[str, Any]:
    return approve_client(client_id)


@app.post("/enrollments/{client_id}/reject", dependencies=[Depends(require_host)])
def reject_enrollment(client_id: str) -> dict[str, Any]:
    return reject_client(client_id)


@app.delete("/enrollments/{client_id}", dependencies=[Depends(require_host)])
def delete_enrollment(client_id: str) -> dict[str, Any]:
    return remove_client(client_id)


# ---------------------------------------------------------------------------
# Distributed Provisioning CSR Endpoints
# ---------------------------------------------------------------------------

@app.post("/enrollments/{client_id}/csr")
async def submit_csr(
    client_id: str,
    request: Request,
    x_nexmesh_client_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Receive client request zip (from `nvflare cert request`), validate, and sign using federation CA."""
    require_client(client_id, x_nexmesh_client_token)
    client = get_client(client_id)

    if client["status"] not in {"APPROVED", "PROVISIONING", "READY"}:
        raise HTTPException(
            status_code=409,
            detail=f"Client must be approved by coordinator before submitting CSR (current status: {client['status']})",
        )

    # Read binary zip payload
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty request body. Expected request.zip bytes.")

    tmp_req_zip = Path(tempfile.gettempdir()) / f"{client_id}-incoming.request.zip"
    tmp_req_zip.write_bytes(body)

    svc = _get_provisioning_service()
    try:
        signed_zip = svc.approve_csr(client_id, tmp_req_zip)
    except ProvisioningError as err:
        raise HTTPException(status_code=500, detail=str(err)) from err
    finally:
        tmp_req_zip.unlink(missing_ok=True)

    with connect() as database:
        database.execute(
            "UPDATE clients SET status = 'AWAITING_CLIENT_PACKAGE', csr_uploaded = 1, signed_package_path = ?, updated_at = ? WHERE id = ?",
            (str(signed_zip), now(), client_id),
        )

    return {
        "status": "AWAITING_CLIENT_PACKAGE",
        "client_id": client_id,
        "signed_response_url": f"/enrollments/{client_id}/signed-response",
        "next_action": "Download signed package and complete local kit assembly using nvflare package",
    }


@app.get("/enrollments/{client_id}/signed-response")
def download_signed_response(
    client_id: str,
    x_nexmesh_client_token: str | None = Header(default=None),
) -> Any:
    require_client(client_id, x_nexmesh_client_token)
    client = get_client(client_id)
    signed_path = client.get("signed_package_path")
    if not signed_path or not os.path.isfile(signed_path):
        raise HTTPException(status_code=404, detail="Signed package not available for this client")

    return FileResponse(
        signed_path,
        media_type="application/zip",
        filename=f"{client_id}.signed.zip",
    )


@app.post("/enrollments/{client_id}/complete-packaging")
def complete_packaging(
    client_id: str,
    x_nexmesh_client_token: str | None = Header(default=None),
) -> dict[str, Any]:
    require_client(client_id, x_nexmesh_client_token)
    with connect() as database:
        database.execute(
            "UPDATE clients SET status = 'READY', updated_at = ? WHERE id = ?",
            (now(), client_id),
        )
    return {"status": "READY", "client_id": client_id, "next_action": "Start NVFlare client"}


# ---------------------------------------------------------------------------
# Client Management Endpoints (Host & Agent)
# ---------------------------------------------------------------------------

@app.post("/clients", status_code=201, dependencies=[Depends(require_host)])
def create_client(request: ClientCreate) -> dict[str, Any]:
    timestamp = now()
    agent_token = secrets.token_urlsafe(32)
    with connect() as database:
        try:
            database.execute(
                """INSERT INTO clients
                (id, display_name, organization, mode, status, dataset_ref, endpoint,
                 capabilities_json, agent_token, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'PENDING', ?, ?, ?, ?, ?, ?)""",
                (
                    request.id,
                    request.display_name,
                    request.organization,
                    request.mode,
                    request.dataset_ref,
                    request.endpoint,
                    json.dumps(request.capabilities),
                    agent_token,
                    timestamp,
                    timestamp,
                ),
            )
        except Exception as error:
            if "UNIQUE constraint failed" in str(error):
                raise HTTPException(status_code=409, detail="client id already exists") from error
            raise
    return get_client(request.id)


@app.get("/clients", dependencies=[Depends(require_host)])
def list_clients(status_filter: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM clients"
    parameters: tuple[str, ...] = ()
    if status_filter:
        query += " WHERE status = ?"
        parameters = (status_filter.upper(),)
    query += " ORDER BY created_at"
    with connect() as database:
        rows = database.execute(query, parameters).fetchall()
    return [serialize(row) for row in rows]


@app.get("/clients/{client_id}", dependencies=[Depends(require_host)])
def read_client(client_id: str) -> dict[str, Any]:
    return get_client(client_id)


@app.patch("/clients/{client_id}", dependencies=[Depends(require_host)])
def update_client(client_id: str, request: ClientUpdate) -> dict[str, Any]:
    current = get_client(client_id)
    updates = request.model_dump(exclude_unset=True)
    if not updates:
        return current
    fields = []
    values: list[Any] = []
    for key, value in updates.items():
        column = "capabilities_json" if key == "capabilities" else key
        fields.append(f"{column} = ?")
        values.append(json.dumps(value) if key == "capabilities" else value)
    fields.append("updated_at = ?")
    values.extend([now(), client_id])
    with connect() as database:
        database.execute(f"UPDATE clients SET {', '.join(fields)} WHERE id = ?", values)
    return get_client(client_id)


@app.post("/clients/{client_id}/approve", dependencies=[Depends(require_host)])
def approve_client(client_id: str) -> dict[str, Any]:
    """Approve a client on the coordinator. Automatically provisions prod_0X for this client only."""
    client = get_client(client_id)
    if client["status"] not in {"PENDING", "REJECTED", "FAILED"}:
        raise HTTPException(status_code=409, detail=f"only pending/failed/rejected clients can be approved (current: {client['status']})")

    org = client.get("organization") or "nvidia"
    with connect() as database:
        database.execute("UPDATE clients SET status = 'APPROVED', updated_at = ? WHERE id = ?", (now(), client_id))

    # Make prod_0X for this specific approved client
    try:
        _execute_client_provisioning(client_id, organization=org)
    except HTTPException:
        # Status was already updated to FAILED in _execute_client_provisioning
        pass

    return get_client(client_id)


@app.post("/clients/{client_id}/reject", dependencies=[Depends(require_host)])
def reject_client(client_id: str) -> dict[str, Any]:
    client = get_client(client_id)
    if client["status"] not in {"PENDING", "APPROVED"}:
        raise HTTPException(status_code=409, detail=f"cannot reject client in state {client['status']}")
    with connect() as database:
        database.execute("UPDATE clients SET status = 'REJECTED', updated_at = ? WHERE id = ?", (now(), client_id))
    return get_client(client_id)


@app.post("/clients/{client_id}/provision", dependencies=[Depends(require_host)])
def provision_client(client_id: str) -> dict[str, Any]:
    client = get_client(client_id)
    if client["status"] not in {"APPROVED", "OFFLINE", "READY", "FAILED"}:
        raise HTTPException(status_code=409, detail="client must be approved before provisioning")
    org = client.get("organization") or "nvidia"
    _execute_client_provisioning(client_id, organization=org)
    return get_client(client_id)


@app.get("/clients/{client_id}/kit", dependencies=[Depends(require_host)])
def download_kit_host(client_id: str, request: Request) -> Any:
    return _kit_response(client_id, request)


@app.get("/agent/{client_id}/kit")
def download_kit_agent(client_id: str, request: Request, x_nexmesh_client_token: str | None = Header(default=None)) -> Any:
    require_client(client_id, x_nexmesh_client_token)
    return _kit_response(client_id, request)


@app.get("/enrollments/{client_id}/kit")
def download_kit_enrollment(client_id: str, request: Request, x_nexmesh_client_token: str | None = Header(default=None)) -> Any:
    require_client(client_id, x_nexmesh_client_token)
    return _kit_response(client_id, request)


def _kit_response(client_id: str, request: Request | None = None) -> Any:
    client = get_client(client_id)
    kit_path = client.get("nvflare_identity")
    if not kit_path or not os.path.isdir(kit_path):
        if client.get("status") in {"APPROVED", "ONLINE", "READY", "OFFLINE", "PROVISIONING", "PROVISIONED"}:
            org = client.get("organization") or "nvidia"
            try:
                _execute_client_provisioning(client_id, organization=org)
                client = get_client(client_id)
                kit_path = client.get("nvflare_identity")
            except Exception:
                pass

    if not kit_path or not os.path.isdir(kit_path):
        raise HTTPException(status_code=404, detail="Kit not provisioned yet for this client")

    with connect() as database:
        row = database.execute("SELECT agent_token FROM clients WHERE id = ?", (client_id,)).fetchone()
        client_token = row[0] if row and row[0] else ""

    server_name = os.getenv("NEXMESH_SERVER_NAME")
    if not server_name:
        req_host = request.url.hostname if request else None
        server_name = req_host if (req_host and req_host not in {"127.0.0.1", "localhost"}) else "127.0.0.1"

    coordinator_url = os.getenv("NEXMESH_COORDINATOR_URL", f"http://{server_name}:8000")

    agent_script_path = Path(__file__).resolve().parent.parent / "agent" / "agent.py"
    req_path = Path(__file__).resolve().parent.parent / "agent" / "requirements.txt"

    requirements_content = req_path.read_text() if req_path.exists() else "requests>=2.32\ntorch>=2.0\ntorchvision>=0.15\nnvflare>=2.9.0\ncertifi\n"
    agent_content = agent_script_path.read_text() if agent_script_path.exists() else ""

    dataset_script_content = (
        "import os\n"
        "import torch\n"
        "from torchvision import datasets\n\n"
        "def main():\n"
        "    os.makedirs('dataset', exist_ok=True)\n"
        "    out_path = 'dataset/mnist.pt'\n"
        "    if os.path.exists(out_path):\n"
        "        print(f'Dataset already exists at {out_path}')\n"
        "        return\n"
        "    print('Downloading MNIST training dataset...')\n"
        "    mnist = datasets.MNIST(root='./mnist_raw', train=True, download=True)\n"
        "    torch.save({'images': mnist.data, 'labels': mnist.targets}, out_path)\n"
        "    print(f'Dataset successfully created at {out_path} ({len(mnist.data)} samples)')\n\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    )

    start_sh_content = (
        "#!/usr/bin/env bash\n"
        "set -e\n\n"
        'DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"\n'
        'cd "$DIR"\n\n'
        'echo "=========================================================="\n'
        f'echo " NexMesh Federated Learning Client Quickstart"\n'
        f'echo " Client ID: {client_id}"\n'
        'echo "=========================================================="\n\n'
        'if [ ! -d ".venv" ]; then\n'
        '    echo "[setup] Creating Python virtual environment in .venv ..."\n'
        '    python3 -m venv .venv\n'
        'fi\n\n'
        'echo "[setup] Activating virtual environment..."\n'
        'source .venv/bin/activate\n\n'
        'echo "[setup] Installing/checking dependencies from requirements.txt..."\n'
        'pip install -q -r requirements.txt\n\n'
        'DATA_PATH="${1:-$NEXMESH_DATA_PATH}"\n'
        'if [ -z "$DATA_PATH" ]; then\n'
        '    if [ -f "dataset/mnist.pt" ]; then\n'
        '        DATA_PATH="dataset/mnist.pt"\n'
        '    else\n'
        '        echo "[setup] No dataset specified. Downloading MNIST into ./dataset/mnist.pt ..."\n'
        '        python3 generate_dataset.py\n'
        '        DATA_PATH="dataset/mnist.pt"\n'
        '    fi\n'
        'fi\n\n'
        'if [ ! -f "$DATA_PATH" ]; then\n'
        '    echo "[error] Dataset not found at: $DATA_PATH"\n'
        '    echo "Usage: ./start.sh [/path/to/dataset.pt]"\n'
        '    exit 1\n'
        'fi\n\n'
        'echo "[setup] Using dataset: $DATA_PATH"\n'
        'echo "[setup] Launching NexMesh client agent..."\n\n'
        f'exec python3 agent.py \\\n'
        f'  --coordinator "{coordinator_url}" \\\n'
        f'  --server-host "{server_name}" \\\n'
        f'  --client-id "{client_id}" \\\n'
        f'  --token "{client_token}" \\\n'
        '  --kit-dir "$DIR" \\\n'
        '  --data-path "$DATA_PATH"\n'
    )

    readme_content = (
        f"# NexMesh Federated Learning Client Kit - {client_id}\n\n"
        "Welcome to the NexMesh federated learning network!\n\n"
        "## Quickstart (One Command)\n\n"
        "### Windows (Command Prompt / PowerShell):\n"
        "Double-click `start.bat` or run in terminal:\n"
        "```cmd\n"
        "start.bat\n"
        "```\n\n"
        "### Linux / macOS / WSL / Git Bash:\n"
        "Run the included start script:\n"
        "```bash\n"
        "bash start.sh\n"
        "```\n"
        "Or provide your own custom dataset:\n"
        "```bash\n"
        "bash start.sh /path/to/my_data.pt\n"
        "```\n\n"
        "## What the startup scripts do automatically:\n"
        "1. Create a local Python virtual environment (`.venv`).\n"
        "2. Install all required packages from `requirements.txt`.\n"
        "3. Download a local MNIST dataset split if you do not have one.\n"
        "4. Auto-detect NVIDIA GPU (CUDA) or fall back to CPU automatically.\n"
        "5. Connect securely to the coordinator and wait for federated training jobs.\n"
    )

    start_bat_content = (
        "@echo off\r\n"
        "setlocal enabledelayedexpansion\r\n\r\n"
        "echo ==========================================================\r\n"
        f"echo  NexMesh Federated Learning Client Quickstart (Windows)\r\n"
        f"echo  Client ID: {client_id}\r\n"
        "echo ==========================================================\r\n\r\n"
        'cd /d "%~dp0"\r\n\r\n'
        "python --version >nul 2>&1\r\n"
        "if %errorlevel% neq 0 (\r\n"
        "    echo [error] Python is not found in PATH. Please install Python 3.10+ from python.org.\r\n"
        "    pause\r\n"
        "    exit /b 1\r\n"
        ")\r\n\r\n"
        'if not exist ".venv" (\r\n'
        '    echo [setup] Creating Python virtual environment in .venv ...\r\n'
        "    python -m venv .venv\r\n"
        ")\r\n\r\n"
        "echo [setup] Activating virtual environment...\r\n"
        "call .venv\\Scripts\\activate.bat\r\n\r\n"
        "echo [setup] Installing/checking dependencies from requirements.txt...\r\n"
        "pip install -q -r requirements.txt\r\n\r\n"
        'set "DATA_PATH=%~1"\r\n'
        'if "%DATA_PATH%"=="" set "DATA_PATH=%NEXMESH_DATA_PATH%"\r\n'
        'if "%DATA_PATH%"=="" (\r\n'
        '    if exist "dataset\\mnist.pt" (\r\n'
        '        set "DATA_PATH=dataset\\mnist.pt"\r\n'
        "    ) else (\r\n"
        "        echo [setup] No dataset specified. Downloading MNIST into dataset\\mnist.pt ...\r\n"
        "        python generate_dataset.py\r\n"
        '        set "DATA_PATH=dataset\\mnist.pt"\r\n'
        "    )\r\n"
        ")\r\n\r\n"
        'if not exist "%DATA_PATH%" (\r\n'
        '    echo [error] Dataset not found at: %DATA_PATH%\r\n'
        "    echo Usage: start.bat [path\\to\\dataset.pt]\r\n"
        "    pause\r\n"
        "    exit /b 1\r\n"
        ")\r\n\r\n"
        "echo [setup] Using dataset: %DATA_PATH%\r\n"
        'set "PYTHONPATH=%~dp0;%PYTHONPATH%"\r\n'
        "echo [setup] Launching NexMesh client agent...\r\n\r\n"
        f"python agent.py ^\r\n"
        f'  --coordinator "{coordinator_url}" ^\r\n'
        f'  --server-host "{server_name}" ^\r\n'
        f'  --client-id "{client_id}" ^\r\n'
        f'  --token "{client_token}" ^\r\n'
        '  --kit-dir "%~dp0." ^\r\n'
        '  --data-path "%DATA_PATH%"\r\n\r\n'
        "if %errorlevel% neq 0 (\r\n"
        "    echo [agent] Exited with code %errorlevel%\r\n"
        "    pause\r\n"
        ")\r\n"
    )

    zip_path = f"/tmp/{client_id}-kit.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Write the NVFlare kit files
        for root, _, files in os.walk(kit_path):
            for file in files:
                full = os.path.join(root, file)
                zf.write(full, os.path.relpath(full, kit_path))

        # 2. Write presetup utilities and scripts
        sitecustomize_content = (
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
        zf.writestr("sitecustomize.py", sitecustomize_content)
        zf.writestr("requirements.txt", requirements_content)
        if agent_content:
            zf.writestr("agent.py", agent_content)
        zf.writestr("generate_dataset.py", dataset_script_content)
        zf.writestr("README.md", readme_content)
        zf.writestr("start.bat", start_bat_content)

        # 3. Write start.sh with executable permissions
        info = zipfile.ZipInfo("start.sh")
        info.external_attr = 0o755 << 16  # rwxr-xr-x
        zf.writestr(info, start_sh_content)

    return FileResponse(zip_path, media_type="application/zip", filename=f"{client_id}-kit.zip")


@app.post("/clients/{client_id}/enable", dependencies=[Depends(require_host)])
def enable_client(client_id: str) -> dict[str, Any]:
    client = get_client(client_id)
    if client["status"] != "DISABLED":
        raise HTTPException(status_code=409, detail="only disabled clients can be enabled")
    with connect() as database:
        database.execute("UPDATE clients SET status = 'APPROVED', updated_at = ? WHERE id = ?", (now(), client_id))
    return get_client(client_id)


@app.post("/clients/{client_id}/disable", dependencies=[Depends(require_host)])
def disable_client(client_id: str) -> dict[str, Any]:
    client = get_client(client_id)
    if client["status"] not in {"APPROVED", "ONLINE", "OFFLINE", "READY"}:
        raise HTTPException(status_code=409, detail="client cannot be disabled from its current state")
    with connect() as database:
        database.execute("UPDATE clients SET status = 'DISABLED', updated_at = ? WHERE id = ?", (now(), client_id))
    return get_client(client_id)


@app.post("/clients/{client_id}/heartbeat")
def heartbeat(client_id: str, _: None = Depends(require_agent)) -> dict[str, Any]:
    client = get_client(client_id)
    if client["status"] not in {"APPROVED", "PROVISIONING", "READY", "ONLINE", "OFFLINE"}:
        raise HTTPException(status_code=409, detail="client is not eligible for heartbeat")
    timestamp = now()
    with connect() as database:
        database.execute(
            "UPDATE clients SET status = 'ONLINE', last_heartbeat = ?, updated_at = ? WHERE id = ?",
            (timestamp, timestamp, client_id),
        )
    return get_client(client_id)


@app.delete("/clients/{client_id}", dependencies=[Depends(require_host)])
def remove_client(client_id: str) -> dict[str, Any]:
    """Delete a client from coordinator: deletes kit from disk, removes from cert.json, deletes DB record."""
    get_client(client_id)  # verifies existence
    svc = _get_provisioning_service()
    svc.remove_client(client_id)
    with connect() as database:
        database.execute("DELETE FROM clients WHERE id = ?", (client_id,))
    return {"status": "DELETED", "id": client_id}


@app.delete("/agent/{client_id}/leave")
@app.post("/agent/{client_id}/leave")
def client_leave(client_id: str, x_nexmesh_client_token: str | None = Header(default=None)) -> dict[str, Any]:
    """Client disconnects/leaves federation voluntarily: cleans up kit and removes client from coordinator."""
    require_client(client_id, x_nexmesh_client_token)
    svc = _get_provisioning_service()
    svc.remove_client(client_id)
    with connect() as database:
        database.execute("DELETE FROM clients WHERE id = ?", (client_id,))
    return {"status": "DELETED", "id": client_id}


# ---------------------------------------------------------------------------
# Agent Endpoints
# ---------------------------------------------------------------------------

@app.get("/agent/{client_id}/status")
def agent_status(client_id: str, x_nexmesh_client_token: str | None = Header(default=None)) -> dict[str, Any]:
    return require_client(client_id, x_nexmesh_client_token)


@app.get("/agent/{client_id}/jobs")
def agent_jobs(client_id: str, x_nexmesh_client_token: str | None = Header(default=None)) -> list[dict[str, Any]]:
    require_client(client_id, x_nexmesh_client_token)
    with connect() as database:
        rows = database.execute("SELECT id FROM jobs WHERE participants_json LIKE ? ORDER BY created_at DESC", (f'%"{client_id}"%',)).fetchall()
    return [read_job(row[0]) for row in rows]


@app.post("/agent/{client_id}/heartbeat")
def agent_heartbeat(client_id: str, x_nexmesh_client_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_client(client_id, x_nexmesh_client_token)
    timestamp = now()
    with connect() as database:
        row = database.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
        if row["status"] not in {"APPROVED", "PROVISIONING", "READY", "ONLINE", "OFFLINE"}:
            raise HTTPException(status_code=409, detail="client is not eligible for heartbeat")
        database.execute(
            "UPDATE clients SET status = 'ONLINE', last_heartbeat = ?, updated_at = ? WHERE id = ?",
            (timestamp, timestamp, client_id),
        )
    return {"status": "ONLINE"}


@app.post("/agent/{client_id}/jobs/{job_id}/result")
def submit_job_result(client_id: str, job_id: str, request: JobResult, x_nexmesh_client_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_client(client_id, x_nexmesh_client_token)
    job = read_job(job_id)
    if client_id not in job["participants"]:
        raise HTTPException(status_code=403, detail="client is not assigned to this job")
    timestamp = now()
    with connect() as database:
        database.execute(
            "UPDATE jobs SET status = ?, result_json = ?, updated_at = ? WHERE id = ?",
            (request.status, json.dumps({"client_id": client_id, **request.metrics, "result_ref": request.result_ref}), timestamp, job_id),
        )
    return read_job(job_id)


# ---------------------------------------------------------------------------
# Jobs Endpoints
# ---------------------------------------------------------------------------

@app.post("/jobs", status_code=201, dependencies=[Depends(require_host)])
def create_job(request: JobCreate) -> dict[str, Any]:
    timestamp = now()
    job_id = f"job-{uuid.uuid4().hex[:10]}"
    with connect() as database:
        database.execute(
            """INSERT INTO jobs
            (id, name, requirements, package_url, participants_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (job_id, request.name, request.requirements, request.package_url, json.dumps(request.participants), timestamp, timestamp),
        )
    return read_job(job_id)


def read_job(job_id: str) -> dict[str, Any]:
    with connect() as database:
        row = database.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    result = dict(row)
    result.pop("admin_output", None)
    result["participants"] = json.loads(result.pop("participants_json"))
    result["result"] = json.loads(result.pop("result_json")) if result.get("result_json") else None
    result.pop("result_json", None)
    return result


def read_job_detail(job_id: str) -> dict[str, Any]:
    with connect() as database:
        row = database.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    result = dict(row)
    result["participants"] = json.loads(result.pop("participants_json"))
    result["result"] = json.loads(result.pop("result_json")) if result.get("result_json") else None
    result.pop("result_json", None)
    return result


def _get_admin_pod() -> str:
    result = _run(
        ["kubectl", "get", "pods", "-l", "app=nvflare-admin", "-o", "jsonpath={.items[0].metadata.name}"],
        capture=True,
    )
    pod = result.stdout.strip()
    if not pod:
        raise HTTPException(status_code=503, detail="nvflare-admin pod not found")
    return pod


def _get_server_pod() -> str:
    result = _run(
        ["kubectl", "get", "pods", "-l", "app=nvflare-server", "-o", "jsonpath={.items[0].metadata.name}"],
        capture=True,
    )
    pod = result.stdout.strip()
    if not pod:
        raise HTTPException(status_code=503, detail="nvflare-server pod not found")
    return pod


def _run(cmd: list[str], capture: bool = False) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=capture, text=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip() if capture else ""
        raise HTTPException(status_code=500, detail=f"command failed: {' '.join(cmd)}\n{detail}")
    return result


@app.post("/jobs/nvflare", status_code=202, dependencies=[Depends(require_host)])
def submit_nvflare_job(request: NVFlareJobSubmit) -> dict[str, Any]:
    jobs_src = os.path.realpath(os.getenv("NEXMESH_JOBS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "jobs")))
    if not os.path.isdir(jobs_src):
        raise HTTPException(status_code=500, detail=f"jobs directory not found: {jobs_src}")

    admin_pod = _get_admin_pod()
    for cmd in [
        ["kubectl", "exec", admin_pod, "--", "rm", "-rf", "/workspace/project"],
        ["kubectl", "exec", admin_pod, "--", "mkdir", "-p", "/workspace/project"],
    ]:
        _run(cmd)
    _run(["kubectl", "cp", jobs_src, f"{admin_pod}:/workspace/project/jobs"])

    min_clients = request.min_clients or len(request.participants)
    server_name = os.getenv("NEXMESH_SERVER_NAME", "192.168.1.43")
    env = {
        "NEXMESH_CLIENTS": ",".join(request.participants),
        "NEXMESH_SERVER_NAME": server_name,
        "NEXMESH_NUM_ROUNDS": str(request.num_rounds),
        "NEXMESH_LOCAL_EPOCHS": str(request.local_epochs),
        "NEXMESH_BATCH_SIZE": str(request.batch_size),
        "NEXMESH_MIN_CLIENTS": str(min_clients),
        "NEXMESH_DATA_PATHS": json.dumps(request.data_paths),
        "NVFLARE_STARTUP_KIT": "/workspace",
        "NVFLARE_USERNAME": "admin@nvidia.com",
    }
    env_str = " ".join(f'{k}="{v}"' for k, v in env.items())
    result = _run(
        ["kubectl", "exec", admin_pod, "--", "sh", "-lc", f"cd /workspace/project && {env_str} python3 jobs/fedavg_nn/job.py"],
        capture=True,
    )

    nvflare_job_id = None
    for line in result.stdout.splitlines():
        if line.startswith("NEXMESH_JOB_ID="):
            nvflare_job_id = line.split("=", 1)[1].strip()

    timestamp = now()
    job_id = f"job-{uuid.uuid4().hex[:10]}"
    admin_output = result.stdout[-2000:] if result.stdout else ""
    with connect() as database:
        database.execute(
            """INSERT INTO jobs (id, name, requirements, participants_json, nvflare_job_id, nvflare_status, status, admin_output, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (job_id, "fedavg_nn", f"rounds={request.num_rounds} epochs={request.local_epochs} batch={request.batch_size}",
             json.dumps(request.participants), nvflare_job_id, "SUBMITTED", "ASSIGNED", admin_output, timestamp, timestamp),
        )
    return {**read_job(job_id), "admin_output": admin_output}


@app.get("/jobs", dependencies=[Depends(require_host)])
def list_jobs() -> list[dict[str, Any]]:
    with connect() as database:
        ids = [row[0] for row in database.execute("SELECT id FROM jobs ORDER BY created_at DESC").fetchall()]
    return [read_job(job_id) for job_id in ids]


@app.get("/jobs/{job_id}", dependencies=[Depends(require_host)])
def get_job(job_id: str) -> dict[str, Any]:
    return read_job_detail(job_id)


@app.get("/jobs/{job_id}/status", dependencies=[Depends(require_host)])
def job_status(job_id: str) -> dict[str, Any]:
    job = read_job_detail(job_id)
    nvflare_job_id = job.get("nvflare_job_id")
    if not nvflare_job_id:
        return {"job_id": job_id, "nvflare_status": job.get("nvflare_status"), "completed": False}

    try:
        server_pod = _get_server_pod()
        result = _run(
            ["kubectl", "exec", server_pod, "--", "test", "-f", "/results/server_test_metrics.jsonl"],
            capture=True,
        )
        completed = result.returncode == 0
    except HTTPException:
        completed = False

    st = "COMPLETED" if completed else job.get("nvflare_status", "SUBMITTED")
    return {"job_id": job_id, "nvflare_job_id": nvflare_job_id, "nvflare_status": st, "completed": completed}


@app.post("/jobs/{job_id}/collect", dependencies=[Depends(require_host)])
def collect_job_results(job_id: str) -> dict[str, Any]:
    job = read_job_detail(job_id)
    if not job.get("nvflare_job_id"):
        raise HTTPException(status_code=400, detail="no NVFlare job submitted for this job")

    server_pod = _get_server_pod()
    tmp_dir = tempfile.mkdtemp(prefix="nexmesh-results-")
    _run(["kubectl", "cp", f"{server_pod}:/results", tmp_dir])

    results_dir = Path(tmp_dir) / "results"
    if not results_dir.exists():
        results_dir = Path(tmp_dir)

    server_metrics = None
    metrics_path = results_dir / "server_test_metrics.jsonl"
    if metrics_path.exists():
        server_metrics = [
            json.loads(line)
            for line in metrics_path.read_text().splitlines()
            if line.strip()
        ]

    summary = None
    summary_path = results_dir / "summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())

    result_payload = {"server_metrics": server_metrics, "summary": summary}
    timestamp = now()
    with connect() as database:
        database.execute(
            "UPDATE jobs SET result_json = ?, status = 'COMPLETED', nvflare_status = 'COMPLETED', updated_at = ? WHERE id = ?",
            (json.dumps(result_payload), timestamp, job_id),
        )
    return read_job_detail(job_id)
