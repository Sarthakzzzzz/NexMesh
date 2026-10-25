import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import yaml

CLIENT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,62}$")
BASE_PARTICIPANTS = {"192.168.1.43", "admin@nvidia.com", "lead@nvidia.com", "org-admin@nvidia.com"}


class ProvisioningError(RuntimeError):
    """Raised when NVFlare participant provisioning fails."""


class NVFlareProvisioningService:
    def __init__(
        self,
        project_file: str | Path = "project.yml",
        workspace: str | Path = "workspace/fedlearn",
        executable: str | None = None,
    ) -> None:
        self.project_file = Path(project_file).resolve()
        self.workspace = Path(workspace).resolve()
        
        # Locate nvflare binary
        candidate_bin = executable or os.getenv("NVFLARE_EXECUTABLE")
        if not candidate_bin:
            in_path = shutil.which("nvflare")
            if in_path:
                candidate_bin = in_path
            else:
                # Look for repo's .venv
                repo_root = Path(__file__).resolve().parent.parent.parent.parent
                venv_bin = repo_root / ".venv" / "bin" / "nvflare"
                if venv_bin.exists():
                    candidate_bin = str(venv_bin)
                else:
                    candidate_bin = "nvflare"
        self.executable = str(candidate_bin)

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        # Ensure NVFlare can write its local audit logs
        tmp_nvflare = Path("/tmp/nvflare")
        tmp_nvflare.mkdir(parents=True, exist_ok=True)
        env["NVFLARE_HOME"] = str(tmp_nvflare)
        return env

    def add_client(self, client_id: str, organization: str = "nvidia") -> Path:
        if not CLIENT_ID_PATTERN.fullmatch(client_id):
            raise ValueError("client_id must contain only lowercase letters, digits, and hyphens")
        if not organization or "\n" in organization or "\r" in organization:
            raise ValueError("organization must be a single non-empty line")
        if not self.project_file.is_file():
            raise FileNotFoundError(self.project_file)

        self.workspace.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="nexmesh-add-client-") as temporary_dir:
            add_client_file = Path(temporary_dir) / "client.yml"
            add_client_file.write_text(
                yaml.safe_dump({"name": client_id, "org": organization}, sort_keys=False),
                encoding="utf-8",
            )
            command = [
                self.executable,
                "provision",
                "--project-file",
                str(self.project_file),
                "--workspace",
                str(self.workspace.parent),
                "--add-client",
                str(add_client_file),
                "--force",
            ]
            result = subprocess.run(
                command,
                cwd=self.project_file.parent,
                capture_output=True,
                text=True,
                check=False,
                env=self._env(),
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout).strip()
                raise ProvisioningError(f"NVFlare provisioning failed: {detail}")

        # Search for newly created kit directory under prod_*
        kit_dir: Optional[Path] = None
        for prod_dir in sorted(self.workspace.glob("prod_*")):
            candidate = prod_dir / client_id
            if candidate.is_dir():
                kit_dir = candidate

        if kit_dir is None:
            raise ProvisioningError(
                f"NVFlare provisioning succeeded but kit not found for client '{client_id}' "
                f"under {self.workspace}/prod_*"
            )
        return kit_dir

    def remove_client(self, client_id: str) -> None:
        """Completely delete client artifacts from disk and from cert.json."""
        # 1. Delete client folder from any prod_*
        for prod_dir in list(self.workspace.glob("prod_*")):
            client_dir = prod_dir / client_id
            if client_dir.exists():
                shutil.rmtree(client_dir, ignore_errors=True)

            # If prod_dir != prod_00, check if any clients remain
            if prod_dir.name != "prod_00":
                remaining_items = [p.name for p in prod_dir.iterdir() if p.is_dir()]
                non_base_clients = [name for name in remaining_items if name not in BASE_PARTICIPANTS]
                if not non_base_clients:
                    # No active clients remain in this prod directory; remove it completely
                    shutil.rmtree(prod_dir, ignore_errors=True)

        # 2. Clean client from workspace/state/cert.json
        cert_json_path = self.workspace / "state" / "cert.json"
        if cert_json_path.exists():
            try:
                cert_data = json.loads(cert_json_path.read_text(encoding="utf-8"))
                if client_id in cert_data:
                    del cert_data[client_id]
                    cert_json_path.write_text(json.dumps(cert_data, indent=2), encoding="utf-8")
            except Exception:
                pass

        # 3. Clean any temp zips
        for tmp_file in Path("/tmp").glob(f"*{client_id}*"):
            if tmp_file.is_file():
                try:
                    tmp_file.unlink(missing_ok=True)
                except Exception:
                    pass

    def get_or_create_ca_dir(self) -> Path:
        """Create or return CA authority directory for distributed provisioning cert signing."""
        ca_dir = self.workspace / "ca"
        ca_dir.mkdir(parents=True, exist_ok=True)
        cert_json_path = self.workspace / "state" / "cert.json"
        if not cert_json_path.exists():
            raise ProvisioningError("Root CA cert.json not found in workspace/state")

        cert_data = json.loads(cert_json_path.read_text(encoding="utf-8"))
        root_cert_pem = cert_data.get("root_cert")
        root_key_pem = cert_data.get("root_pri_key")
        if not root_cert_pem or not root_key_pem:
            raise ProvisioningError("root_cert or root_pri_key missing from state/cert.json")

        (ca_dir / "rootCA.pem").write_text(root_cert_pem, encoding="utf-8")
        (ca_dir / "rootCA.key").write_text(root_key_pem, encoding="utf-8")

        # Compute SHA-256 fingerprint for ca.json
        try:
            from nvflare.tool.cert.cert_commands import cert_fingerprint_sha256
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend

            cert = x509.load_pem_x509_certificate(root_cert_pem.encode("utf-8"), default_backend())
            fingerprint = cert_fingerprint_sha256(cert)
        except Exception:
            # Fallback direct computation
            import hashlib
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend

            cert = x509.load_pem_x509_certificate(root_cert_pem.encode("utf-8"), default_backend())
            digest = hashlib.sha256(cert.public_bytes(x509.Encoding.DER)).hexdigest().upper()
            fingerprint = "SHA256:" + ":".join(digest[i : i + 2] for i in range(0, len(digest), 2))

        ca_meta = {
            "project": "fedlearn",
            "created_at": "2026-10-24T14:26:24+00:00",
            "provision_version": "00",
            "rootCA.pem": fingerprint,
        }
        (ca_dir / "ca.json").write_text(json.dumps(ca_meta, indent=2), encoding="utf-8")
        return ca_dir

    def get_or_create_project_profile(self) -> Path:
        """Create or return project_profile.yaml required for nvflare cert approve."""
        profile_path = self.workspace.parent.parent / "project_profile.yaml"
        if not profile_path.exists():
            profile_path = self.workspace / "project_profile.yaml"
        profile_content = {
            "name": "fedlearn",
            "scheme": "grpc",
            "connection_security": "mtls",
            "server": {
                "host": os.getenv("NEXMESH_SERVER_NAME", "192.168.1.43"),
                "fed_learn_port": int(os.getenv("NEXMESH_FED_LEARN_PORT", "8002")),
                "admin_port": int(os.getenv("NEXMESH_ADMIN_PORT", "8003")),
            },
        }
        profile_path.write_text(yaml.safe_dump(profile_content, sort_keys=False), encoding="utf-8")
        return profile_path

    def approve_csr(self, client_id: str, request_zip_path: Path) -> Path:
        """Sign client's request zip using federation CA and return path to signed zip."""
        ca_dir = self.get_or_create_ca_dir()
        profile_path = self.get_or_create_project_profile()
        output_signed_zip = Path(tempfile.gettempdir()) / f"{client_id}.signed.zip"

        command = [
            self.executable,
            "cert",
            "approve",
            str(request_zip_path.resolve()),
            "--ca-dir",
            str(ca_dir),
            "--profile",
            str(profile_path),
            "--out",
            str(output_signed_zip),
            "--force",
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            env=self._env(),
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise ProvisioningError(f"NVFlare certificate approval failed: {detail}")

        if not output_signed_zip.exists():
            raise ProvisioningError(f"Signed zip was not produced at {output_signed_zip}")

        return output_signed_zip
