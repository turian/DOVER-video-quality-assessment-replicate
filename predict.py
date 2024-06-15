import json
import os
import pickle as pkl
import random
import sys

import numpy as np
import torch
import yaml
from cog import BasePredictor, Input, Path
from tqdm import tqdm

DOVER_PATH = "/DOVER"

sys.path.append(DOVER_PATH)

# Importing necessary modules from the DOVER package
from dover.datasets import (
    UnifiedFrameSampler,
    ViewDecompositionDataset,
    spatial_temporal_view_decomposition,
)
from dover.models import DOVER


class Predictor(BasePredictor):
    def setup(self):
        """Setup to load the model and configurations"""
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # Load configuration
        config_path = os.path.join(DOVER_PATH, "dover.yml")
        with open(config_path, "r") as f:
            self.opt = yaml.safe_load(f)

        # Initialize and load the model
        self.model = DOVER(**self.opt["model"]["args"]).to(self.device)
        self.model.load_state_dict(
            torch.load(
                os.path.join(DOVER_PATH, self.opt["test_load_path"]),
                map_location=self.device,
            )
        )
        self.model.eval()

        self.mean = torch.FloatTensor([123.675, 116.28, 103.53]).to(self.device)
        self.std = torch.FloatTensor([58.395, 57.12, 57.375]).to(self.device)

    def predict(
        self, video: Path = Input(description="Video to quality assess"), seed: int = 42
    ) -> str:
        """Predict method to process video and output scores"""
        # Set seed for reproducibility
        self.set_seed(seed)

        video_path = str(video)

        dopt = self.opt["data"]["val-l1080p"]["args"]
        dopt["anno_file"] = None
        dopt["data_prefix"] = os.path.dirname(video_path)

        temporal_samplers = {}
        for stype, sopt in dopt["sample_types"].items():
            if "t_frag" not in sopt:
                temporal_samplers[stype] = UnifiedFrameSampler(
                    sopt["clip_len"], sopt["num_clips"], sopt["frame_interval"]
                )
            else:
                temporal_samplers[stype] = UnifiedFrameSampler(
                    sopt["clip_len"] // sopt["t_frag"],
                    sopt["t_frag"],
                    sopt["frame_interval"],
                    sopt["num_clips"],
                )

        # View Decomposition
        views, _ = spatial_temporal_view_decomposition(
            video_path, dopt["sample_types"], temporal_samplers
        )

        for k, v in views.items():
            num_clips = dopt["sample_types"][k].get("num_clips", 1)
            views[k] = (
                ((v.to(self.device).permute(1, 2, 3, 0) - self.mean) / self.std)
                .permute(3, 0, 1, 2)
                .reshape(v.shape[0], num_clips, -1, *v.shape[2:])
                .transpose(0, 1)
            )

        results = [np.mean(r.cpu().numpy()) for r in self.model(views)]
        fused_results = self.fuse_results(results)

        return json.dumps(fused_results)

    def fuse_results(self, results):
        """Fuse aesthetic and technical results into final scores"""
        t, a = (results[1] - 0.1107) / 0.07355, (results[0] + 0.08285) / 0.03774
        x = t * 0.6104 + a * 0.3896
        return {
            "aesthetic": 1 / (1 + np.exp(-a)),
            "technical": 1 / (1 + np.exp(-t)),
            "overall": 1 / (1 + np.exp(-x)),
        }

    def set_seed(self, seed):
        """Set the seed for reproducibility"""
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        if self.device == "cuda":
            torch.cuda.manual_seed_all(seed)
