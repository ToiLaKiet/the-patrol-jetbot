"""Convert a normalized GNM waypoint to forward/turn velocities without hardware.

Controller adapted from PlaceNav (MIT); see place_recognition/LICENSE.PlaceNav.
"""

import argparse
import math
from numbers import Real


def waypoint_to_velocity(waypoint, max_v, max_w, frame_rate=5.0):
    """Return (v m/s, w rad/s) for one normalized [x, y, cos_yaw, sin_yaw] or [x, y].

    x points forward; y and w are positive to the left. Position is scaled
    internally by max_v/frame_rate, following GNM deployment. Pass unscaled
    predictions, not metric coordinates. Limits must be calibrated for JetBot.
    Behind-robot waypoints clamp forward velocity to zero, following PlaceNav.
    Raises ValueError for invalid input;
    the motor owner must stop on errors. This function has no watchdog.
    """
    if not all(isinstance(x, Real) and math.isfinite(x)
               for x in (max_v, max_w, frame_rate)):
        raise ValueError("Velocity limits and frame rate must be finite numbers")
    if max_v <= 0 or max_w < 0 or frame_rate <= 0:
        raise ValueError("Require max_v > 0, max_w >= 0 and frame_rate > 0")

    try:
        valid = len(waypoint) in (2, 4) and all(
            isinstance(x, Real) and math.isfinite(x) for x in waypoint
        )
        if valid:
            dx, dy = waypoint[:2]
    except (TypeError, ValueError, KeyError):
        valid = False
    if not valid:
        raise ValueError("Waypoint must be a flat sequence of 2 or 4 finite numbers")

    if len(waypoint) == 4 and waypoint[2] == 0 and waypoint[3] == 0:
        raise ValueError("Waypoint heading must have a nonzero direction")

    # GNM normalizes positions during training; deployment scales to the target robot.
    scale = max_v / frame_rate
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("Waypoint scale must be finite and positive")
    dx, dy = dx * scale, dy * scale
    if not all(math.isfinite(x) for x in (dx, dy)):
        raise ValueError("Scaled waypoint must be finite")

    if abs(dx) < 1e-8 and abs(dy) < 1e-8:
        v, w = 0.0, 0.0
        if len(waypoint) == 4:
            heading = math.atan2(waypoint[3], waypoint[2])
            w = ((heading + math.pi) % (2 * math.pi) - math.pi) * frame_rate
    elif abs(dx) < 1e-8:
        v = 0.0
        w = math.copysign(math.pi / 2, dy) * frame_rate
    else:
        v = dx * frame_rate
        w = math.atan(dy / dx) * frame_rate

    return max(0.0, min(v, max_v)), max(-max_w, min(w, max_w))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Đổi waypoint normalized sang (v, w), không mở motor.")
    parser.add_argument("--waypoint", type=float, nargs="+", required=True)
    parser.add_argument("--max-v", type=float, required=True, help="Giới hạn vận tốc tiến, m/s.")
    parser.add_argument("--max-w", type=float, required=True, help="Giới hạn vận tốc quay, rad/s.")
    parser.add_argument("--frame-rate", type=float, default=5.0, help="Tần số điều khiển, Hz (mặc định: 5).")
    args = parser.parse_args()
    try:
        v, w = waypoint_to_velocity(args.waypoint, args.max_v, args.max_w, args.frame_rate)
    except ValueError as error:
        parser.error(str(error))
    print("v={:.6f} m/s, w={:.6f} rad/s".format(v, w))
