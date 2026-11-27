"""Bayesian PlaceNav core: ordered BGR observations -> normalized waypoints -> (v, w).

Adapted from PlaceNav (MIT; see place_recognition/LICENSE.PlaceNav).
"""

from collections import deque
import math
from numbers import Integral, Real
import time

import torch

from utils import preprocess_frame
from .inference import read_frame
from .pd_controller import waypoint_to_velocity


def navigate(observations, localizer, waypoint_model, max_v, max_w, frame_rate=5.0,
             goal_node_idx=-1, lookahead=1, target_waypoint_idx=2):
    """Yield navigation results from (timestamp_seconds, BGR_frame) observations.

    Create the Bayesian localizer and GNM once per session. Timestamps must be
    finite and increase; duplicates are skipped. Six observations warm up GNM.
    Frames must already be sampled at the desired cadence. No camera or motor
    is opened here, and timestamps are not compared to a live clock.
    Goal detection follows PlaceNav's node equality and yields zero velocities.
    Errors propagate; any future motor caller must stop on errors and exit.
    """
    waypoint_to_velocity([0, 0], max_v, max_w, frame_rate)
    map_size = len(localizer.map_paths)
    if map_size == 0 or not isinstance(goal_node_idx, Integral) or not -1 <= goal_node_idx < map_size:
        raise ValueError("Goal index không hợp lệ hoặc topomap rỗng.")
    goal_node_idx = map_size - 1 if goal_node_idx == -1 else goal_node_idx
    if not isinstance(lookahead, Integral) or lookahead < 1:
        raise ValueError("lookahead phải là số nguyên >= 1.")
    if (not isinstance(target_waypoint_idx, Integral)
            or not 0 <= target_waypoint_idx < waypoint_model.len_trajectory_pred):
        raise ValueError("Chỉ số waypoint không hợp lệ.")

    device = next(waypoint_model.parameters()).device
    topomap = [preprocess_frame(read_frame(path)).unsqueeze(0) for path in localizer.map_paths]
    context = deque(maxlen=waypoint_model.context_size + 1)
    last_timestamp = None
    for timestamp, frame in observations:
        started = time.perf_counter()
        if not isinstance(timestamp, Real) or not math.isfinite(timestamp):
            raise ValueError("Timestamp phải hữu hạn.")
        if last_timestamp is not None:
            if timestamp < last_timestamp:
                raise ValueError("Ảnh phải theo thứ tự timestamp tăng dần.")
            if timestamp == last_timestamp:
                continue
        # shortcut: check ordering only; add a capture-age watchdog before live motor use.
        context.append(preprocess_frame(frame).unsqueeze(0))
        last_timestamp = timestamp
        if len(context) < context.maxlen:
            continue

        timings = {"preprocess": (time.perf_counter() - started) * 1000, "localize": 0.0,
                   "batch": 0.0, "gnm": 0.0, "controller": 0.0}
        # The existing Bayesian match initializes its belief on the first query.
        stage_started = time.perf_counter()
        node, posterior = localizer.match(frame)
        timings["localize"] = (time.perf_counter() - stage_started) * 1000
        if not isinstance(node, Integral) or not 0 <= node < map_size:
            raise ValueError("Bayesian trả node ngoài topomap.")
        if not isinstance(posterior, Real) or not math.isfinite(posterior) or not 0 <= posterior <= 1:
            raise ValueError("Bayesian trả posterior không hợp lệ.")
        subgoal = min(node + lookahead, goal_node_idx)
        reached_goal = node == goal_node_idx
        distance = waypoints = chosen = None
        v, w = 0.0, 0.0
        if not reached_goal:
            stage_started = time.perf_counter()
            model_context = torch.cat(list(context), dim=1).to(device)
            timings["batch"] = (time.perf_counter() - stage_started) * 1000
            stage_started = time.perf_counter()
            with torch.no_grad():
                distance_tensor, prediction = waypoint_model(model_context, topomap[subgoal].to(device))
            if (tuple(distance_tensor.shape) != (1, 1)
                    or tuple(prediction.shape) != (1, waypoint_model.len_trajectory_pred, 4)
                    or not torch.isfinite(distance_tensor).all().item()
                    or not torch.isfinite(prediction).all().item()):
                raise ValueError("GNM phải trả distance [1, 1] và waypoint [1, 5, 4] hữu hạn.")
            distance = distance_tensor[0, 0].item()
            waypoints = prediction[0].cpu().numpy()
            timings["gnm"] = (time.perf_counter() - stage_started) * 1000
            stage_started = time.perf_counter()
            chosen = waypoints[target_waypoint_idx]
            v, w = waypoint_to_velocity(chosen, max_v, max_w, frame_rate)
            timings["controller"] = (time.perf_counter() - stage_started) * 1000

        yield {
            "timestamp": timestamp, "node": node, "posterior": posterior,
            "subgoal": subgoal, "distance": distance, "waypoints": waypoints,
            "chosen_waypoint": chosen, "v": v, "w": w, "reached_goal": reached_goal,
            "time_ms": (time.perf_counter() - started) * 1000,
            "timings_ms": {name: round(value, 1) for name, value in timings.items()},
        }
        if reached_goal:
            return

    if len(context) < context.maxlen:
        raise ValueError("Cần ít nhất {} ảnh mới để tạo context GNM.".format(context.maxlen))
