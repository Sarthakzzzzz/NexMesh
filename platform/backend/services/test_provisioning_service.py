from pathlib import Path
from unittest.mock import patch

from .provisioning_service import NVFlareProvisioningService


def test_add_client_uses_supported_nvflare_arguments(tmp_path: Path) -> None:
    project_file = tmp_path / "project.yml"
    project_file.write_text("api_version: 3\nparticipants: []\n", encoding="utf-8")
    service = NVFlareProvisioningService(project_file=project_file, workspace=tmp_path / "workspace")

    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        # Create expected dummy kit
        kit = tmp_path / "workspace" / "prod_00" / "site-4"
        kit.mkdir(parents=True)
        result = service.add_client("site-4")

    assert result == kit.resolve()
    command = run.call_args.args[0]
    assert command[1] == "provision"
    assert "--add-client" in command
    assert command[-1] == "--force"
