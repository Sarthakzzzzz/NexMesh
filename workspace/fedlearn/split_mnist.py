import os
import torch
from torchvision import datasets


NUM_CLIENTS = 3
DATASET_SIZE_PER_CLIENT = 20_000

OUTPUT_DIR = "./datasets"
SERVER_TEST_DIR = "./server_test"


def main():
    print("Downloading/loading MNIST...")

    mnist = datasets.MNIST(
        root="./mnist_raw",
        train=True,
        download=True,
    )
    test_mnist = datasets.MNIST(
        root="./mnist_raw",
        train=False,
        download=True,
    )

    images = mnist.data
    labels = mnist.targets

    print(f"Total MNIST training samples: {len(images)}")

    if len(images) < NUM_CLIENTS * DATASET_SIZE_PER_CLIENT:
        raise ValueError("Not enough MNIST samples.")

    generator = torch.Generator().manual_seed(42)
    indices = torch.randperm(len(images), generator=generator)

    for client_id in range(NUM_CLIENTS):
        start = client_id * DATASET_SIZE_PER_CLIENT
        end = start + DATASET_SIZE_PER_CLIENT

        client_indices = indices[start:end]

        client_images = images[client_indices]
        client_labels = labels[client_indices]

        client_dir = os.path.join(
            OUTPUT_DIR,
            f"client_{client_id + 1}"
        )

        os.makedirs(client_dir, exist_ok=True)

        output_file = os.path.join(
            client_dir,
            "mnist.pt"
        )

        torch.save(
            {
                "images": client_images,
                "labels": client_labels,
            },
            output_file,
        )

        print(
            f"client_{client_id + 1}: "
            f"{len(client_images)} samples -> {output_file}"
        )

    os.makedirs(SERVER_TEST_DIR, exist_ok=True)
    torch.save(
        {"images": test_mnist.data, "labels": test_mnist.targets},
        os.path.join(SERVER_TEST_DIR, "mnist.pt"),
    )
    print(f"server_test: {len(test_mnist.data)} samples -> {SERVER_TEST_DIR}/mnist.pt")

    print("\nMNIST split completed.")


if __name__ == "__main__":
    main()