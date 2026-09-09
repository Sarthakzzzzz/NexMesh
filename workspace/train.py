import os
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import TensorDataset, DataLoader


BATCH_SIZE = 64
EPOCHS = 1
LEARNING_RATE = 0.001

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

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
        x = self.features(x)
        x = self.classifier(x)
        return x

def load_client_dataset(client_data_path):
    print(f"Loading dataset from: {client_data_path}")

    if not os.path.exists(client_data_path):
        raise FileNotFoundError(
            f"Dataset not found: {client_data_path}"
        )

    data = torch.load(
        client_data_path,
        map_location="cpu"
    )

    images = data["images"].float() / 255.0
    labels = data["labels"].long()

    # MNIST images are [N, 28, 28].
    # CNN expects [N, 1, 28, 28].
    images = images.unsqueeze(1)

    dataset = TensorDataset(images, labels)

    print(f"Loaded {len(dataset)} samples")

    return dataset

def train(model, dataloader):
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

        images = images.to(DEVICE)
        labels = labels.to(DEVICE)

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

    average_loss = total_loss / len(dataloader)

    accuracy = 100.0 * correct / total

    return average_loss, accuracy

def evaluate(model, dataloader):
    model.eval()

    criterion = nn.CrossEntropyLoss()

    total_loss = 0.0
    correct = 0
    total = 0

    with torch.no_grad():

        for images, labels in dataloader:

            images = images.to(DEVICE)
            labels = labels.to(DEVICE)

            outputs = model(images)

            loss = criterion(outputs, labels)

            total_loss += loss.item()

            predictions = outputs.argmax(dim=1)

            correct += (
                predictions == labels
            ).sum().item()

            total += labels.size(0)

    average_loss = total_loss / len(dataloader)

    accuracy = 100.0 * correct / total

    return average_loss, accuracy

def main():

    print("=" * 60)
    print("MNIST LOCAL TRAINING")
    print("=" * 60)

    print(f"Device: {DEVICE}")

    client_id = os.environ.get("CLIENT_ID", "1")

    dataset_path = (
        f"/data/client_{client_id}/mnist.pt"
    )

    print(f"Client: {client_id}")
    print(f"Dataset: {dataset_path}")


    dataset = load_client_dataset(dataset_path)

    dataloader = DataLoader(
        dataset,
        batch_size=BATCH_SIZE,
        shuffle=True,
    )


    model = MNISTCNN().to(DEVICE)

    print("\nModel:")
    print(model)

    print("\nStarting local training...")

    for epoch in range(EPOCHS):

        loss, accuracy = train(
            model,
            dataloader
        )

        print(
            f"Epoch {epoch + 1}/{EPOCHS} "
            f"| Loss: {loss:.4f} "
            f"| Accuracy: {accuracy:.2f}%"
        )

    output_path = (
        f"/tmp/client_{client_id}_model.pt"
    )

    torch.save(
        model.state_dict(),
        output_path
    )

    print(
        f"\nLocal model saved to: {output_path}"
    )

    print("\nLocal training completed.")


if __name__ == "__main__":
    main()
