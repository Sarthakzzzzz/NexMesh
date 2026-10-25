import json
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from nvflare.apis.fl_context import FLContext
from nvflare.app_common.abstract.fl_model import FLModel
from nvflare.app_common.abstract.model import ModelLearnableKey
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
        if event_type != AppEventType.ROUND_DONE:
            return

        global_weights = fl_ctx.get_prop(AppConstants.GLOBAL_MODEL)
        weights_dict = None
        if global_weights and isinstance(global_weights, dict):
            if ModelLearnableKey.WEIGHTS in global_weights:
                weights_dict = global_weights[ModelLearnableKey.WEIGHTS]
            elif "weights" in global_weights:
                weights_dict = global_weights["weights"]
            elif AppConstants.MODEL_WEIGHTS in global_weights:
                weights_dict = global_weights[AppConstants.MODEL_WEIGHTS]
            else:
                weights_dict = global_weights

        if not weights_dict or not isinstance(weights_dict, dict):
            try:
                run_dir = fl_ctx.get_engine().get_workspace().get_run_dir(fl_ctx.get_job_id())
                ckpt_file = Path(run_dir) / "app_server" / "FL_global_model.pt"
                if ckpt_file.exists():
                    data = torch.load(ckpt_file, map_location="cpu")
                    weights_dict = data.get("model", data.get("model_state_dict", data))
                    if isinstance(weights_dict, dict) and "weights" in weights_dict:
                        weights_dict = weights_dict["weights"]
            except Exception:
                pass

        if not weights_dict or not isinstance(weights_dict, dict):
            return

        params = {}
        for name, value in weights_dict.items():
            if isinstance(value, torch.Tensor):
                params[name] = value
            elif hasattr(value, "__array__") or isinstance(value, (list, tuple)):
                params[name] = torch.as_tensor(value)

        if not params:
            return

        current_round = fl_ctx.get_prop(AppConstants.CURRENT_ROUND)
        if current_round is None:
            current_round = 0

        self.log_info(fl_ctx, f"Evaluating global model at round {current_round}...")
        try:
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
                "round": int(current_round),
                "loss": total_loss / len(dataset),
                "accuracy": 100.0 * total_correct / len(dataset),
                "samples": len(dataset),
            }
            self.log_info(fl_ctx, f"Server evaluation round {current_round}: loss={result['loss']:.4f}, acc={result['accuracy']:.2f}%")
            results_dir = Path(self.results_dir)
            results_dir.mkdir(parents=True, exist_ok=True)
            metrics_path = results_dir / "server_test_metrics.jsonl"
            with metrics_path.open("a") as stream:
                stream.write(json.dumps(result) + "\n")
            torch.save({"model_state_dict": params}, results_dir / "final_global_model.pt")
            rounds = [json.loads(line) for line in metrics_path.read_text().splitlines()]
            (results_dir / "summary.json").write_text(json.dumps({"rounds": rounds}, indent=2) + "\n")
        except Exception as e:
            self.log_error(fl_ctx, f"Failed in ServerMNISTEvaluator: {e}")
