import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("NEXMESH_HOST_TOKEN", "host-test")
os.environ.setdefault("NEXMESH_AGENT_TOKEN", "agent-test")
os.environ.setdefault(
    "NEXMESH_DATABASE_PATH",
    str(Path(tempfile.gettempdir()) / "nexmesh-smoke.db"),
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.main import app


def main() -> None:
    database_path = Path(os.environ["NEXMESH_DATABASE_PATH"])
    database_path.unlink(missing_ok=True)

    with TestClient(app) as client:
        host_headers = {"Authorization": "Bearer host-test"}
        response = client.get("/health")
        assert response.status_code == 200, response.text

        response = client.post(
            "/clients",
            headers=host_headers,
            json={
                "id": "site-4",
                "display_name": "Site 4",
                "mode": "managed_kubernetes",
                "dataset_ref": "site-4-data",
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "PENDING"

        response = client.post("/clients/site-4/approve", headers=host_headers)
        assert response.json()["status"] in {"APPROVED", "READY"}

        response = client.post(
            "/clients/site-4/heartbeat",
            headers={"X-NexMesh-Agent-Token": "agent-test"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "ONLINE"

        response = client.post("/clients/site-4/disable", headers=host_headers)
        assert response.json()["status"] == "DISABLED"

        response = client.delete("/clients/site-4", headers=host_headers)
        assert response.status_code in {200, 202}, response.text
        assert response.json()["status"] == "DELETED"

    print("Coordinator smoke test: OK")


if __name__ == "__main__":
    main()
