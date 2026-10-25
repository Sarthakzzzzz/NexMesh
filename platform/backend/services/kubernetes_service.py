from dataclasses import dataclass

import yaml


@dataclass(frozen=True)
class ManagedClientSpec:
    client_id: str
    image: str = "fedlearn/nvflare:local"
    kit_node_path: str | None = None
    dataset_node_path: str | None = None
    data_path: str | None = None
    gpu: int = 0
    namespace: str = "default"


def render_managed_client(spec: ManagedClientSpec) -> str:
    """Render a local-Kind managed client Deployment.

    The caller must provide kit/data paths that already exist on the node.
    Production PVC and Secret-backed resources should use a separate renderer.
    """
    if not spec.client_id:
        raise ValueError("client_id is required")
    kit_node_path = spec.kit_node_path or f"/nvflare-kits/{spec.client_id}"
    dataset_node_path = spec.dataset_node_path or f"/datasets/client_{spec.client_id.rsplit('-', 1)[-1]}"
    data_path = spec.data_path or f"/data/client_{spec.client_id.rsplit('-', 1)[-1]}"

    container = {
        "name": spec.client_id,
        "image": spec.image,
        "imagePullPolicy": "IfNotPresent",
        "command": [
            "/bin/sh",
            "-c",
            "rm -f /workspace/pid.fl /workspace/daemon_pid.fl /workspace/restart.fl /workspace/shutdown.fl && exec /workspace/startup/sub_start.sh --once",
        ],
        "volumeMounts": [
            {"name": "site-kit", "mountPath": "/workspace"},
            {"name": "site-data", "mountPath": data_path, "readOnly": True},
        ],
    }
    pod_spec = {
        "containers": [container],
        "volumes": [
            {
                "name": "site-kit",
                "hostPath": {"path": kit_node_path, "type": "Directory"},
            },
            {
                "name": "site-data",
                "hostPath": {"path": dataset_node_path, "type": "Directory"},
            },
        ],
    }
    if spec.gpu:
        pod_spec["runtimeClassName"] = "nvidia"
        container["resources"] = {"limits": {"nvidia.com/gpu": spec.gpu}}

    document = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": spec.client_id, "namespace": spec.namespace},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": {"app": spec.client_id}},
            "template": {
                "metadata": {"labels": {"app": spec.client_id}},
                "spec": pod_spec,
            },
        },
    }
    return yaml.safe_dump(document, sort_keys=False)
