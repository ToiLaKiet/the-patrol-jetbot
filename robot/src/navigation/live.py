"""Live Repeat: inference in a worker; only the main loop may command motors."""

import math
from queue import Empty, Full, Queue
import threading
import time

from safety.safety import SafetyInput
from .pd_controller import waypoint_to_velocity


def run_live(camera, motors, safety, localizer, model, max_v, max_w, wheelbase,
             v_full, min_posterior, frame_rate=5.0, goal_node_idx=-1,
             lookahead=1, target_waypoint_idx=2):
    """Use a started camera; stop motors on goal, timeout, error or Ctrl+C.

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
    stopped = threading.Event()
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
                raise RuntimeError("CAMERA_LOST: context bị gián đoạn.")
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
            for result in navigate(observations(), localizer, model, max_v, max_w,
                                   frame_rate, goal_node_idx, lookahead, target_waypoint_idx):
                publish(result)
                print("node={node} posterior={posterior:.4f} subgoal={subgoal} "
                      "v={v:.4f} w={w:.4f} goal={reached_goal} time_ms={time_ms:.1f}".format(
                          **result), flush=True)
            publish(None)
        except BaseException as error:
            publish(error)

    # shortcut: Python watchdog cannot survive a process/driver stall; add a motor-side watchdog for that.
    worker = threading.Thread(target=infer, daemon=True)
    try:
        started = time.monotonic()
        first_result_deadline = started + (model.context_size + 1) / frame_rate + safety.cfg.cmd_timeout
        worker.start()
        last_result = None
        while True:
            try:
                result = results.get(timeout=0.02)
            except Empty:
                result = None
            else:
                if isinstance(result, BaseException):
                    raise result
                if result is None:
                    return
                last_result = result

            frame_time = camera.last_frame_time
            now = time.monotonic()
            if ((frame_time is None and now - started > safety.cfg.cmd_timeout)
                    or (frame_time is not None and not 0 <= now - frame_time <= safety.cfg.cmd_timeout)):
                raise RuntimeError("CAMERA_LOST: camera không có ảnh mới.")
            if last_result is None:
                if now > first_result_deadline:
                    raise RuntimeError("INFERENCE_TIMEOUT: chưa nhận được waypoint đầu tiên.")
                continue
            state = SafetyInput(
                now=time.monotonic(), last_cmd_t=last_result["timestamp"],
                localized=last_result["posterior"] >= min_posterior,
                need_camera=True, camera_ok=frame_time is not None,
                battery=None,
            )
            # Check even zero commands so stale data cannot keep a session alive.
            reason = safety.check(state)
            if reason != "OK":
                raise RuntimeError("Dừng navigation: " + reason)
            if result is not None:
                v, w, reason = safety.filter(result["v"], result["w"], state)
                if reason != "OK":
                    raise RuntimeError("Dừng navigation: " + reason)
                if result["reached_goal"] or (v == 0 and w == 0):
                    motors.stop()
                else:
                    motors.drive(v, w, wheelbase, v_full)
                if result["reached_goal"]:
                    return
    finally:
        stopped.set()
        motors.stop()
