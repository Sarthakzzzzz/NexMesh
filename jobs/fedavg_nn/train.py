import argparse
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import TensorDataset, DataLoader
import nvflare.client as flare


BATCH_SIZE = 64
EPOCHS = 1
LEARNING_RATE = 0.001


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


def load_dataset(path):
    data = torch.load(path, map_location="cpu")

    images = data["images"].float() / 255.0
    labels = data["labels"].long()

    images = images.unsqueeze(1)

    return TensorDataset(images, labels)


def train(model, dataloader, device):
    model.train()

    criterion = nn.CrossEntropyLoss()

    optimizer = optim.Adam(
        model.parameters(),
        lr=LEARNING_RATE
    )

    total_loss = 0.0
    correct = 0
    total = 0

    for images, labels in dataloader:
        images = images.to(device)
        labels = labels.to(device)

        optimizer.zero_grad()

        outputs = model(images)

        loss = criterion(outputs, labels)

        loss.backward()
        optimizer.step()

        total_loss += loss.item()

        predictions = outputs.argmax(dim=1)

        correct += (
            predictions == labels
        ).sum().item()

        total += labels.size(0)

    return (
        total_loss / len(dataloader),
        100.0 * correct / total
    )


def main():
    flare.init()

    parser = argparse.ArgumentParser()

    site_name = flare.get_site_name()
    client_id = site_name.split("-")[-1]

    data_path = f"/data/client_{client_id}/mnist.pt"

    parser.add_argument(
        "--data_path",
        type=str,
        default=data_path,
    )

    parser.add_argument(
        "--epochs",
        type=int,
        default=EPOCHS,
    )

    parser.add_argument(
        "--batch_size",
        type=int,
        default=BATCH_SIZE,
    )

    args = parser.parse_args()

    data_path = args.data_path

    device = torch.device(
        "cuda" if torch.cuda.is_available() else "cpu"
    )

    site_name = flare.get_site_name()

    print(f"Site: {site_name}")
    print(f"Device: {device}")
    if device.type != "cuda":
        raise RuntimeError("CUDA is required for this proof; no GPU is available")

    if torch.cuda.is_available():
        print(
            f"GPU: {torch.cuda.get_device_name(0)}"
        )

    dataset = load_dataset(data_path)

    dataloader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True
    )

    model = MNISTCNN().to(device)

    while flare.is_running():
        input_model = flare.receive()

        if input_model is None:
            break

        model.load_state_dict(
            input_model.params
        )

        model = model.to(device)

        for epoch in range(args.epochs):
            loss, accuracy = train(
                model,
                dataloader,
                device
            )

            print(
                f"site={site_name} "
                f"round={input_model.current_round} "
                f"epoch={epoch + 1}/{args.epochs} "
                f"loss={loss:.4f} "
                f"accuracy={accuracy:.2f}%"
            )

        params = {
            name: param.detach().cpu().clone()
            for name, param in model.state_dict().items()
        }

        output_model = flare.FLModel(
            params=params,
            metrics={
                "loss": loss,
                "accuracy": accuracy
            }
        )

        flare.send(output_model)


if __name__ == "__main__":
    main()