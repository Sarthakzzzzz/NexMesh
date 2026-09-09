import json
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from nvflare.apis.fl_context import FLContext
from nvflare.app_common.abstract.fl_model import FLModel
from nvflare.app_common.app_constant import AppConstants
from nvflare.app_common.app_event_type import AppEventType
from nvflare.app_common.utils.fl_model_utils import FLModelUtils
from nvflare.apis.shareable import Shareable
from nvflare.widgets.widget import Widget


class MNISTCNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1, 32, 3), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3), nn.ReLU(), nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(), nn.Linear(64 * 5 * 5, 128), nn.ReLU(), nn.Linear(128, 10)
        )

    def forward(self, images):
        return self.classifier(self.features(images))


class ServerMNISTEvaluator(Widget):
    def __init__(self, test_path="/data/server_test/mnist.pt", results_dir="/results"):
        super().__init__()
        self.test_path = test_path
        self.results_dir = str(results_dir)

    def handle_event(self, event_type: str, fl_ctx: FLContext):
        if event_type != AppEventType.AFTER_AGGREGATION:
            return
        aggregated_result = fl_ctx.get_prop(AppConstants.AGGREGATION_RESULT)
        if isinstance(aggregated_result, FLModel):
            aggregated_model = aggregated_result
        elif isinstance(aggregated_result, Shareable):
            aggregated_model = FLModelUtils.from_shareable(aggregated_result)
        else:
            return
        params = aggregated_model.params
        if not isinstance(params, dict):
            return
        params = {name: value for name, value in params.items() if isinstance(value, torch.Tensor)}
        if not params:
            return
        model = MNISTCNN()
        model.load_state_dict(params)
        model.eval()
        test = torch.load(self.test_path, map_location="cpu")
        dataset = TensorDataset(test["images"].float().div(255).unsqueeze(1), test["labels"].long())
        loader = DataLoader(dataset, batch_size=256)
        loss_fn = nn.CrossEntropyLoss(reduction="sum")
        total_loss = total_correct = 0
        with torch.no_grad():
            for images, labels in loader:
                outputs = model(images)
                total_loss += loss_fn(outputs, labels).item()
                total_correct += (outputs.argmax(1) == labels).sum().item()
        result = {
            "round": int(getattr(aggregated_model, "current_round", 0)),
            "loss": total_loss / len(dataset),
            "accuracy": 100.0 * total_correct / len(dataset),
            "samples": len(dataset),
        }
        results_dir = Path(self.results_dir)
        results_dir.mkdir(parents=True, exist_ok=True)
        metrics_path = results_dir / "server_test_metrics.jsonl"
        with metrics_path.open("a") as stream:
            stream.write(json.dumps(result) + "\n")
        torch.save({"model_state_dict": params}, results_dir / "final_global_model.pt")
        rounds = [json.loads(line) for line in metrics_path.read_text().splitlines()]
        (results_dir / "summary.json").write_text(json.dumps({"rounds": rounds}, indent=2) + "\n")