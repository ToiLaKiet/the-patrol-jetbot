"""Live Repeat: inference in a worker; only the main loop may command motors."""

import math
from queue import Empty, Full, Queue
import threading
import time

from safety.safety import SafetyInput
from .pd_controller import waypoint_to_velocity


def _warmup_models(localizer, model):
    """Initialize both forward paths on the inference thread without updating belief."""
    import torch

    from utils import preprocess_frame
    from .inference import read_frame

    frame = read_frame(localizer.map_paths[0])
    localizer.extractor(frame)
    device = next(model.parameters()).device
    goal = preprocess_frame(frame).unsqueeze(0).to(device)
    context = goal.repeat(1, model.context_size + 1, 1, 1)
    with torch.no_grad():
        distance, waypoints = model(context, goal)
        if not torch.isfinite(distance).all().item() or not torch.isfinite(waypoints).all().item():
            raise ValueError("Warm-up GNM trả NaN/Inf.")


def run_live(camera, motors, safety, localizer, model, max_v, max_w, wheelbase,
             v_full, min_posterior, frame_rate=5.0, goal_node_idx=-1,
             lookahead=1, target_waypoint_idx=2, startup_timeout=30.0):
    """Warm up, start camera, then stop motors on goal, timeout, error or Ctrl+C.

    The caller owns camera cleanup. A daemon worker may finish late, but never
    owns the motors. Timeout is measured from frame arrival, not result arrival.
    """
    motors.stop()
    from .navigate import navigate

    waypoint_to_velocity([0, 0], max_v, max_w, frame_rate)
    if not all(math.isfinite(x) and x > 0 for x in (wheelbase, v_full)):
        raise ValueError("wheelbase và v_full phải hữu hạn và > 0.")
    if not math.isfinite(min_posterior) or not 0 < min_posterior <= 1:
        raise ValueError("min_posterior phải hữu hạn và trong (0, 1].")
    if not math.isfinite(startup_timeout) or startup_timeout <= 0:
        raise ValueError("startup_timeout phải hữu hạn và > 0.")
    stopped = threading.Event()
    warmed_up = threading.Event()
    camera_ready = threading.Event()
    results = Queue(maxsize=1)

    def observations():
        last_timestamp = None
        next_sample = time.monotonic()
        while not stopped.is_set():
            if stopped.wait(max(0.0, next_sample - time.monotonic())):
                return
            observation = camera.get_observation()
            if observation is None or observation[0] == last_timestamp:
                stopped.wait(0.01)
                continue
            timestamp, frame = observation
            if time.monotonic() - timestamp > safety.cfg.cmd_timeout:
                raise RuntimeError("CAMERA_LOST: ảnh camera quá hạn.")
            if last_timestamp is not None and timestamp - last_timestamp > safety.cfg.cmd_timeout:
                print("LIVE: khoảng cách ảnh {:.2f}s; bỏ context cũ, gom lại {} ảnh mới.".format(
                    timestamp - last_timestamp, model.context_size + 1), flush=True)
            last_timestamp = timestamp
            next_sample = time.monotonic() + 1.0 / frame_rate
            yield timestamp, frame

    def publish(item):
        while not stopped.is_set():
            try:
                results.put(item, timeout=0.02)
                return
            except Full:
                pass

    def infer():
        try:
            warmup_started = time.monotonic()
            print("LIVE: warm-up CosPlace + GNM; motor đang dừng.", flush=True)
            _warmup_models(localizer, model)
            if stopped.is_set():
                return
            print("LIVE: warm-up xong sau {:.2f}s; chờ mở camera.".format(
                time.monotonic() - warmup_started), flush=True)
            warmed_up.set()
            while not camera_ready.wait(0.02):
                if stopped.is_set():
                    return
            if stopped.is_set():
                return
            print("LIVE: gom {} ảnh camera mới.".format(model.context_size + 1), flush=True)
            for result in navigate(observations(), localizer, model, max_v, max_w,
                                   frame_rate, goal_node_idx, lookahead, target_waypoint_idx,
                                   safety.cfg.cmd_timeout):
                print("node={node} posterior={posterior:.4f} subgoal={subgoal} "
                      "v={v:.4f} w={w:.4f} goal={reached_goal} time_ms={time_ms:.1f} timings_ms={}".format(
                          result.get("timings_ms", {}), **result), flush=True)
                publish(result)
            publish(None)
        except BaseException as error:
            publish(error)

    # shortcut: Python watchdog cannot survive a process/driver stall; add a motor-side watchdog for that.
    worker = threading.Thread(target=infer, daemon=True)
    try:
        started = time.monotonic()
        first_result_deadline = started + startup_timeout
        worker.start()
        last_result = None
        startup_reason = None
        while True:
            try:
                result = results.get(timeout=0.02)
            except Empty:
                result = None
            else:
                if isinstance(result, BaseException):
                    raise result
                if result is None:
                    if last_result is None:
                        raise RuntimeError("Navigation kết thúc trước waypoint hợp lệ đầu tiên: "
                                           + (startup_reason or "chưa có kết quả"))
                    return

            if warmed_up.is_set() and not camera_ready.is_set():
                print("LIVE: mở camera sau warm-up; motor đang dừng.", flush=True)
                camera_open_started = time.monotonic()
                camera.start()
                # Warm-up and camera opening must not consume the first-frame budget.
                first_result_deadline = time.monotonic() + startup_timeout
                print("LIVE: camera mở sau {:.2f}s; chờ frame/waypoint đầu tối đa {:.1f}s.".format(
                    time.monotonic() - camera_open_started, startup_timeout), flush=True)
                camera_ready.set()
            frame_time = camera.last_frame_time
            now = time.monotonic()
            if camera_ready.is_set():
                if frame_time is None and now > first_result_deadline:
                    raise RuntimeError("CAMERA_LOST: chưa nhận callback frame đầu tiên sau khi mở camera.")
                if frame_time is not None and not 0 <= now - frame_time <= safety.cfg.cmd_timeout:
                    raise RuntimeError("CAMERA_LOST: callback frame đã dừng cập nhật; "
                                       "tuổi frame {:.2f}s, giới hạn {:.2f}s.".format(
                                           now - frame_time, safety.cfg.cmd_timeout))
            if last_result is None and now > first_result_deadline:
                raise RuntimeError("INFERENCE_TIMEOUT: chưa nhận được waypoint hợp lệ đầu tiên sau {:.1f}s "
                                   "({}); lý do gần nhất: {}.".format(
                                       startup_timeout, "map + context + inference"
                                       if camera_ready.is_set() else "warm-up", startup_reason or "chưa có kết quả"))
            candidate = result if result is not None else last_result
            if candidate is None:
                continue
            state = SafetyInput(
                now=time.monotonic(), last_cmd_t=candidate["timestamp"],
                localized=candidate["posterior"] >= min_posterior,
                need_camera=True, camera_ok=frame_time is not None,
                battery=None,
            )
            # Check even zero commands so stale data cannot keep a session alive.
            reason = safety.check(state)
            if reason != "OK":
                if last_result is None and reason in ("CMD_TIMEOUT", "LOCALIZATION_LOST"):
                    motors.stop()
                    startup_reason = reason
                    print("LIVE: motor vẫn dừng; bỏ waypoint khởi động {} "
                          "(tuổi {:.3f}s, posterior {:.4f}); chờ kết quả hợp lệ.".format(
                              reason, state.now - state.last_cmd_t, candidate["posterior"]), flush=True)
                    continue
                raise RuntimeError("Dừng navigation: {} (tuổi waypoint {:.3f}s, giới hạn {:.3f}s; "
                                   "posterior {:.4f}, ngưỡng {:.4f}).".format(
                                       reason, state.now - state.last_cmd_t, safety.cfg.cmd_timeout,
                                       candidate["posterior"], min_posterior))
            if result is not None:
                v, w, reason = safety.filter(result["v"], result["w"], state)
                if reason != "OK":
                    raise RuntimeError("Dừng navigation: " + reason)
                last_result = result
                if result["reached_goal"] or (v == 0 and w == 0):
                    motors.stop()
                else:
                    motors.drive(v, w, wheelbase, v_full)
                if result["reached_goal"]:
                    return
    finally:
        stopped.set()
        motors.stop()
