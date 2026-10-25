import os
import sys
import tempfile
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ["NEXMESH_HOST_TOKEN"] = "host-secret-test"
os.environ["NEXMESH_AGENT_TOKEN"] = "agent-secret-test"
os.environ["NEXMESH_DATABASE_PATH"] = str(Path(tempfile.gettempdir()) / "nexmesh-workflow-test.db")

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from main import app, connect


def test_full_workflow():
    db_path = Path(os.environ["NEXMESH_DATABASE_PATH"])
    db_path.unlink(missing_ok=True)

    with TestClient(app) as client:
        host_hdr = {"Authorization": "Bearer host-secret-test"}

        # 1. Health check
        r = client.get("/health")
        assert r.status_code == 200

        # 2. Client requests connection (status should be PENDING, no kit generated)
        r = client.post("/client-requests", json={"display_name": "Hospital X"})
        assert r.status_code == 201
        data = r.json()
        client_id = data["client_id"]
        client_token = data["client_token"]
        assert data["status"] == "PENDING"

        # Verify client is in database as PENDING with no nvflare_identity
        with connect() as conn:
            row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
            assert row is not None
            assert row["status"] == "PENDING"
            assert row["nvflare_identity"] is None

        # 3. Duplicate enrollment prevention via /enrollments
        r = client.post("/enrollments", json={"id": client_id, "display_name": "Hospital X"})
        assert r.status_code == 409

        # 4. Check enrollment status
        r = client.get(f"/enrollments/{client_id}/status", headers={"X-Nexmesh-Client-Token": client_token})
        assert r.status_code == 200
        assert r.json()["status"] == "PENDING"
        assert "Waiting" in r.json()["next_action"]

        # 5. Kit download before approval must be rejected
        r = client.get(f"/agent/{client_id}/kit", headers={"X-Nexmesh-Client-Token": client_token})
        assert r.status_code == 404

        # 6. Unauthorized download attempt rejected
        r = client.get(f"/agent/{client_id}/kit", headers={"X-Nexmesh-Client-Token": "bad-token"})
        assert r.status_code == 401

        # 7. Approve client -> Triggers provisioning for this specific client
        fake_kit_dir = Path(tempfile.mkdtemp(prefix="fake-kit-"))
        (fake_kit_dir / "startup").mkdir(parents=True)
        (fake_kit_dir / "startup" / "fed_client.json").write_text("{}")
        (fake_kit_dir / "startup" / "sub_start.sh").write_text("#!/bin/sh\n")

        def fake_prov(cid, organization="nvidia"):
            with connect() as conn:
                conn.execute(
                    "UPDATE clients SET status = 'READY', nvflare_identity = ? WHERE id = ?",
                    (str(fake_kit_dir), cid),
                )
            return fake_kit_dir

        with patch("main._execute_client_provisioning", side_effect=fake_prov):
            r = client.post(f"/clients/{client_id}/approve", headers=host_hdr)
            assert r.status_code == 200
            assert r.json()["status"] == "READY"
            assert r.json()["nvflare_identity"] == str(fake_kit_dir)

        # 8. Kit download now succeeds with valid client token
        r = client.get(f"/agent/{client_id}/kit", headers={"X-Nexmesh-Client-Token": client_token})
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"

        # 9. Cross-client token download rejected
        r = client.get(f"/agent/{client_id}/kit", headers={"X-Nexmesh-Client-Token": "other-token"})
        assert r.status_code == 401

        # 10. Agent Heartbeat updates status to ONLINE
        r = client.post(f"/agent/{client_id}/heartbeat", headers={"X-Nexmesh-Client-Token": client_token})
        assert r.status_code == 200
        assert r.json()["status"] == "ONLINE"

        # 11. Coordinator deletes client -> Client deleted from DB and kit cleaned
        with patch.object(app.state if hasattr(app, "state") else app, "dummy", create=True):
            r = client.delete(f"/clients/{client_id}", headers=host_hdr)
            assert r.status_code == 200
            assert r.json()["status"] == "DELETED"

        # Verify client is gone from DB
        with connect() as conn:
            row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
            assert row is None

        # 12. Client voluntary leave test:
        r2 = client.post("/enrollments", json={"id": "client-leave-test", "display_name": "Hospital Y"})
        assert r2.status_code == 201
        token2 = r2.json()["client_token"]

        r_leave = client.post("/agent/client-leave-test/leave", headers={"X-Nexmesh-Client-Token": token2})
        assert r_leave.status_code == 200
        assert r_leave.json()["status"] == "DELETED"

        with connect() as conn:
            row = conn.execute("SELECT * FROM clients WHERE id = 'client-leave-test'").fetchone()
            assert row is None

    print("Coordinator workflow tests PASSED successfully!")


if __name__ == "__main__":
    test_full_workflow()
