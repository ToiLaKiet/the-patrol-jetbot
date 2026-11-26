"""GNM Large from PlaceNav (MIT; see place_recognition/LICENSE.PlaceNav)."""

from pathlib import Path
import pickle
from types import SimpleNamespace

import torch
from torch import nn
from torch.nn import functional as F
from torchvision.models import mobilenet_v2


class GNM(nn.Module):
    """Architecture of the published gnm_large.pth: 6 images, 5 waypoints, heading."""

    context_size = 5
    len_trajectory_pred = 5
    num_action_params = 4
    learn_angle = True

    def __init__(self):
        super().__init__()
        self.obs_mobilenet = mobilenet_v2(pretrained=False).features
        self.goal_mobilenet = mobilenet_v2(pretrained=False).features
        self.obs_mobilenet[0][0] = nn.Conv2d(18, 32, 3, stride=2, padding=1, bias=False)
        self.goal_mobilenet[0][0] = nn.Conv2d(21, 32, 3, stride=2, padding=1, bias=False)
        self.compress_observation = nn.Sequential(nn.Linear(1280, 1024), nn.ReLU())
        self.compress_goal = nn.Sequential(
            nn.Linear(1280, 1024), nn.ReLU(), nn.Linear(1024, 1024), nn.ReLU(),
        )
        self.linear_layers = nn.Sequential(
            nn.Linear(2048, 256), nn.ReLU(), nn.Linear(256, 32), nn.ReLU(),
        )
        self.dist_predictor = nn.Sequential(nn.Linear(32, 1))
        self.action_predictor = nn.Sequential(nn.Linear(32, 20))

    def forward(self, context, goal):
        observation = F.adaptive_avg_pool2d(self.obs_mobilenet(context), 1).flatten(1)
        observation = self.compress_observation(observation)
        goal_input = torch.cat((context, goal), dim=1)
        goal_features = F.adaptive_avg_pool2d(self.goal_mobilenet(goal_input), 1).flatten(1)
        goal_features = self.compress_goal(goal_features)
        features = self.linear_layers(torch.cat((observation, goal_features), dim=1))
        distance = self.dist_predictor(features)
        actions = self.action_predictor(features).reshape(-1, 5, 4)
        positions = torch.cumsum(actions[:, :, :2], dim=1)
        headings = F.normalize(actions[:, :, 2:], dim=-1)
        return distance, torch.cat((positions, headings), dim=-1)


class _GNMUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        # The published checkpoint embeds a model from the original training package.
        if module == "gnm_train.models.gnm" and name == "GNM":
            return GNM
        return super().find_class(module, name)


def load_gnm(checkpoint, device="cuda"):
    """Load the trusted published GNM Large checkpoint on CPU, then move to device.

    This checkpoint contains pickled Python objects; only load trusted weights.
    No training package, ROS, PlaceNav checkout or network download is needed.
    """
    checkpoint = Path(checkpoint)
    if not checkpoint.is_file():
        raise FileNotFoundError("Không thấy checkpoint GNM: " + str(checkpoint))
    if device not in ("cpu", "cuda"):
        raise ValueError("device phải là cpu hoặc cuda.")
    if device == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA chưa khả dụng; kiểm tra môi trường hoặc chọn --device cpu.")

    checkpoint_pickle = SimpleNamespace(
        Unpickler=_GNMUnpickler, load=pickle.load, __name__="pickle",
    )
    saved = torch.load(str(checkpoint), map_location="cpu", pickle_module=checkpoint_pickle)
    if not isinstance(saved, dict) or "model" not in saved:
        raise ValueError("Checkpoint GNM phải chứa model.")
    trained = saved["model"]
    if isinstance(trained, nn.DataParallel):
        trained = trained.module
    if not isinstance(trained, GNM):
        raise ValueError("Checkpoint không chứa model GNM Large.")
    model = GNM()
    model.load_state_dict(trained.state_dict(), strict=True)
    del trained, saved
    return model.eval().to(torch.device(device))
