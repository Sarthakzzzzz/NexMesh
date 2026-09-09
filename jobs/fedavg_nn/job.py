import torch.nn as nn

from nvflare.app_opt.pt.recipes.fedavg import FedAvgRecipe
from nvflare.recipe import ProdEnv
from nvflare.recipe.utils import set_per_site_config

from server_evaluator import ServerMNISTEvaluator


class MNISTCNN(nn.Module):
    def __init__(self):
        super().__init__()

        self.features = nn.Sequential(
            nn.Conv2d(1, 32, kernel_size=3),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, kernel_size=3),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )

        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(64 * 5 * 5, 128),
            nn.ReLU(),
            nn.Linear(128, 10),
        )

    def forward(self, x):
        return self.classifier(self.features(x))


def main():
    recipe = FedAvgRecipe(
        name="fedavg_nn",
        min_clients=3,
        num_rounds=5,
        model=MNISTCNN(),
        train_script="jobs/fedavg_nn/train.py",
        train_args="--epochs 1 --batch_size 64",
        launch_external_process=True,
    )

    set_per_site_config(recipe, {
        "site-1": {"train_args": "--data_path /data/client_1/mnist.pt --epochs 1 --batch_size 64"},
        "site-2": {"train_args": "--data_path /data/client_2/mnist.pt --epochs 1 --batch_size 64"},
        "site-3": {"train_args": "--data_path /data/client_3/mnist.pt --epochs 1 --batch_size 64"},
    })

    recipe._job.add_file_to_server("jobs/fedavg_nn/server_evaluator.py", dest_dir="custom")
    recipe._job.to_server(ServerMNISTEvaluator(), id="server_mnist_evaluator")

    env = ProdEnv(
        startup_kit_location="/workspace",
        username="admin@nvidia.com",
    )

    run = recipe.execute(env)

    print("Job Status:", run.get_status())
    print("Result:", run.get_result())


if __name__ == "__main__":
    main()
