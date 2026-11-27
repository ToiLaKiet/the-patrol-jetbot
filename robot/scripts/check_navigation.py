"""CPU checks for GNM loading and Bayesian navigation; never opens hardware."""

import io
import math
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cv2
import numpy as np
import torch

from navigation.gnm import GNM, _GNMUnpickler, load_gnm
from navigation.navigate import navigate
from navigation.place_recognition.bayesian_querier import PlaceRecognitionTopologicalFilter


class FakeGNM(torch.nn.Module):
    context_size = 5
    len_trajectory_pred = 5

    def __init__(self):
        super().__init__()
        self.anchor = torch.nn.Parameter(torch.zeros(1))
        self.contexts, self.goals = [], []
        self.prediction = torch.tensor([[
            [0.1, 0.01, 1, 0], [0.2, 0.02, 1, 0], [0.3, 0.03, 1, 0],
            [0.4, 0.04, 1, 0], [0.5, 0.05, 1, 0],
        ]])
        self.distance = torch.ones(1, 1)

    def forward(self, context, goal):
        self.contexts.append(context.clone())
        self.goals.append(goal.clone())
        return self.distance, self.prediction


class NavigationChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.paths = [Path(self.directory.name) / (str(i) + ".png") for i in range(3)]
        for i, path in enumerate(self.paths):
            self.assertTrue(cv2.imwrite(str(path), np.full((64, 85, 3), i * 40, np.uint8)))
        self.localizer = SimpleNamespace(map_paths=self.paths, match=Mock(return_value=(0, 0.9)))
        self.model = FakeGNM()

    def observations(self, count=7):
        return [(i / 5, np.full((64, 85, 3), i * 10, np.uint8)) for i in range(count)]

    def run_core(self, observations=None, **options):
        return list(navigate(self.observations() if observations is None else observations,
                             self.localizer, self.model, max_v=0.1, max_w=0.6, **options))

    def test_context_order_subgoal_and_single_scale(self):
        results = self.run_core()
        self.assertEqual(len(results), 2)
        self.assertEqual(self.localizer.match.call_count, 2)
        self.assertEqual(tuple(self.model.contexts[0].shape), (1, 18, 64, 85))
        self.assertEqual(tuple(self.model.goals[0].shape), (1, 3, 64, 85))
        self.assertAlmostEqual(self.model.contexts[0][0, 0, 0, 0].item(), -0.485 / 0.229, places=5)
        self.assertAlmostEqual(self.model.contexts[1][0, 0, 0, 0].item(), (10 / 255 - 0.485) / 0.229, places=5)
        self.assertAlmostEqual(self.model.goals[0][0, 0, 0, 0].item(), (40 / 255 - 0.485) / 0.229, places=5)
        self.assertEqual(results[0]["subgoal"], 1)
        self.assertAlmostEqual(results[0]["chosen_waypoint"][0], 0.3)
        self.assertAlmostEqual(results[0]["v"], 0.03)
        self.assertAlmostEqual(results[0]["w"], math.atan(0.1) * 5, places=6)

    def test_real_bayesian_initializes_once_and_retains_belief(self):
        querier = PlaceRecognitionTopologicalFilter(np.eye(3))
        self.localizer.match = lambda frame: querier.match(np.array([1, 0, 0]))
        results = self.run_core()
        self.assertEqual([r["node"] for r in results], [0, 0])
        self.assertTrue(np.isfinite(querier.belief).all())
        self.assertGreater(results[1]["posterior"], 0.9)

    def test_duplicate_observations_do_not_fill_context_or_update_bayesian(self):
        observations = self.observations(count=6)
        observations.insert(1, observations[0])
        results = self.run_core(observations)
        self.assertEqual(len(results), 1)
        self.assertEqual(self.localizer.match.call_count, 1)

    def test_goal_yields_stop_without_predicting_or_consuming_more_frames(self):
        self.localizer.match.return_value = (2, 0.99)
        results = self.run_core()
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["reached_goal"])
        self.assertEqual((results[0]["v"], results[0]["w"]), (0, 0))
        self.assertIsNone(results[0]["chosen_waypoint"])
        self.assertEqual(len(self.model.contexts), 0)
        self.assertEqual(self.localizer.match.call_count, 1)

    def test_lookahead_is_clamped_to_custom_goal(self):
        result = self.run_core(lookahead=10, goal_node_idx=1)[0]
        self.assertEqual(result["subgoal"], 1)

    def test_live_camera_through_real_core_to_motor(self):
        from navigation.live import run_live
        from safety.safety import SafetyLayer

        frame = self.observations(1)[0][1]

        class Camera:
            @property
            def last_frame_time(self):
                return time.monotonic()

            def get_observation(self):
                return time.monotonic(), frame.copy()

        motors = Mock()
        self.localizer.extractor = Mock()
        self.localizer.match.side_effect = [(0, 0.9), (2, 0.99)]
        with patch("builtins.print"):
            run_live(Camera(), motors, SafetyLayer(), self.localizer, self.model,
                     max_v=0.1, max_w=0.6, wheelbase=0.1, v_full=0.5,
                     min_posterior=0.7, frame_rate=20)
        motors.drive.assert_called_once()
        self.assertAlmostEqual(motors.drive.call_args[0][0], 0.03)
        motors.stop.assert_called()
        self.assertEqual(len(self.model.contexts), 2)
        self.localizer.extractor.assert_called_once()
        self.assertEqual(self.localizer.match.call_count, 2)

    def test_bad_observations_and_configuration(self):
        for observations in ([], self.observations(5),
                             [(math.nan, self.observations(1)[0][1])],
                             self.observations() + [(0, self.observations(1)[0][1])]):
            with self.subTest(observations=len(observations)):
                with self.assertRaises(ValueError):
                    self.run_core(observations)
        for options in ({"goal_node_idx": 3}, {"goal_node_idx": -2},
                        {"lookahead": 0}, {"target_waypoint_idx": -1},
                        {"target_waypoint_idx": 5}, {"frame_rate": 0}):
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    self.run_core(**options)
        self.localizer.map_paths = []
        with self.assertRaises(ValueError):
            self.run_core()

    def test_bad_localization_and_predictions(self):
        for match in ((-1, 0.9), (3, 0.9), (0, math.nan), (0, 1.1)):
            self.localizer.match.return_value = match
            with self.subTest(match=match):
                with self.assertRaises(ValueError):
                    self.run_core()
        self.localizer.match.return_value = (0, 0.9)
        original = self.model.prediction
        for prediction in (torch.zeros(1, 5, 2), torch.full((1, 5, 4), math.nan),
                           torch.zeros(1, 5, 4), -original):
            self.model.prediction = prediction
            with self.subTest(shape=tuple(prediction.shape)):
                with self.assertRaises(ValueError):
                    self.run_core()
        self.model.prediction = original
        self.model.distance = torch.full((1, 1), math.inf)
        with self.assertRaises(ValueError):
            self.run_core()

    def test_checkpoint_loader_errors_and_legacy_class_mapping(self):
        with self.assertRaises(FileNotFoundError):
            load_gnm(Path(self.directory.name) / "missing.pth", "cpu")
        path = Path(self.directory.name) / "invalid.pth"
        torch.save({"model": {}}, str(path))
        for device in ("cpu", "invalid"):
            with self.assertRaises(ValueError):
                load_gnm(path, device)
        self.assertIs(_GNMUnpickler(io.BytesIO()).find_class("gnm_train.models.gnm", "GNM"), GNM)

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "checkpoints/gnm_large.pth").is_file(),
                         "Cần checkpoint GNM Large tin cậy để thử loader/forward thật")
    def test_published_checkpoint_on_cpu(self):
        path = Path(__file__).resolve().parents[1] / "checkpoints/gnm_large.pth"
        model = load_gnm(path, "cpu")
        self.assertFalse(model.training)
        with torch.no_grad():
            distance, waypoints = model(torch.zeros(1, 18, 64, 85), torch.zeros(1, 3, 64, 85))
        self.assertEqual(tuple(distance.shape), (1, 1))
        self.assertEqual(tuple(waypoints.shape), (1, 5, 4))
        self.assertTrue(torch.isfinite(waypoints).all().item())
        self.assertAlmostEqual(waypoints[0, 2, 0].item(), 0.9002967, places=4)
        self.assertTrue(torch.allclose(torch.norm(waypoints[:, :, 2:], dim=-1),
                                       torch.ones(1, 5), atol=1e-5))


if __name__ == "__main__":
    unittest.main(verbosity=2)
