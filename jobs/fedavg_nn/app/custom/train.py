import argparse
import os

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import TensorDataset, DataLoader, Subset

import nvflare.client as flare


BATCH_SIZE = 64
EPOCHS = 1
LEARNING_RATE = 0.001


class MNISTCNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1, 32, kernel_size=3), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(32, 64, kernel_size=3), nn.ReLU(), nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(64 * 5 * 5, 128), nn.ReLU(),
            nn.Linear(128, 10),
        )

    def forward(self, x):
        return self.classifier(self.features(x))


def load_dataset(path, test_ratio=0.2, seed=42):
    data = torch.load(path, map_location="cpu", weights_only=True)
    images = data["images"].float().unsqueeze(1) / 255.0
    labels = data["labels"].long()
    dataset = TensorDataset(images, labels)
    g = torch.Generator().manual_seed(seed)
    idx = torch.randperm(len(dataset), generator=g)
    split = int(len(dataset) * test_ratio)
    return Subset(dataset, idx[split:].tolist()), Subset(dataset, idx[:split].tolist())


def run_epoch(model, loader, device, optimizer=None, criterion=None):
    if criterion is None:
        criterion = nn.CrossEntropyLoss()
    training = optimizer is not None
    model.train() if training else model.eval()
    total_loss, correct, total = 0.0, 0, 0
    ctx = torch.enable_grad() if training else torch.no_grad()
    with ctx:
        for imgs, lbls in loader:
            imgs, lbls = imgs.to(device), lbls.to(device)
            out = model(imgs)
            loss = criterion(out, lbls)
            if training:
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
            total_loss += loss.item()
            correct += (out.argmax(1) == lbls).sum().item()
            total += lbls.size(0)
    return total_loss / len(loader), 100.0 * correct / total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_path", default=os.environ.get("NEXMESH_DATA_PATH", ""))
    parser.add_argument("--epochs", type=int, default=int(os.environ.get("NEXMESH_EPOCHS", "1")))
    parser.add_argument("--batch_size", type=int, default=int(os.environ.get("NEXMESH_BATCH_SIZE", "64")))
    args = parser.parse_args()

    if not args.data_path:
        raise ValueError("data_path must be set via --data_path or NEXMESH_DATA_PATH env var")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    flare.init()
    site_name = flare.get_site_name()
    if torch.cuda.is_available():
        print(f"Site: {site_name} | Device: {device} ({torch.cuda.get_device_name(0)})")
    else:
        print(f"Site: {site_name} | No GPU detected. Automatically switched to CPU.")

    use_cuda = device.type == "cuda"
    num_workers = 2 if os.cpu_count() and os.cpu_count() > 1 else 0
    train_set, test_set = load_dataset(args.data_path)
    train_loader = DataLoader(train_set, batch_size=args.batch_size, shuffle=True, num_workers=num_workers, pin_memory=use_cuda)
    test_loader = DataLoader(test_set, batch_size=256, num_workers=num_workers, pin_memory=use_cuda)

    model = MNISTCNN().to(device)
    criterion = nn.CrossEntropyLoss()

    while flare.is_running():
        input_model = flare.receive()
        if input_model is None:
            break

        model.load_state_dict(input_model.params)
        model = model.to(device)
        optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)

        for epoch in range(args.epochs):
            train_loss, train_acc = run_epoch(model, train_loader, device, optimizer, criterion)
            print(f"site={site_name} round={input_model.current_round} epoch={epoch+1}/{args.epochs} loss={train_loss:.4f} acc={train_acc:.2f}%")

        test_loss, test_acc = run_epoch(model, test_loader, device, criterion=criterion)

        flare.send(flare.FLModel(
            params={k: v.detach().cpu().clone() for k, v in model.state_dict().items()},
            metrics={"train_loss": train_loss, "train_accuracy": train_acc, "test_loss": test_loss, "test_accuracy": test_acc},
        ))


if __name__ == "__main__":
    main()
