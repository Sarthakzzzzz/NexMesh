import yaml

from .kubernetes_service import ManagedClientSpec, render_managed_client


def test_render_managed_client_is_site_scoped() -> None:
    rendered = yaml.safe_load(
        render_managed_client(
            ManagedClientSpec(
                client_id="site-4",
                kit_node_path="/nvflare-kits/site-4",
                dataset_node_path="/datasets/client_4",
                data_path="/data/client_4",
                gpu=1,
            )
        )
    )
    pod = rendered["spec"]["template"]["spec"]
    container = pod["containers"][0]
    assert rendered["metadata"]["name"] == "site-4"
    assert pod["runtimeClassName"] == "nvidia"
    assert container["resources"]["limits"]["nvidia.com/gpu"] == 1
    assert pod["volumes"][0]["hostPath"]["path"] == "/nvflare-kits/site-4"
    assert pod["volumes"][1]["hostPath"]["path"] == "/datasets/client_4"
    assert container["volumeMounts"][1]["mountPath"] == "/data/client_4"
