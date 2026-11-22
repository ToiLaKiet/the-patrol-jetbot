"""Standalone Mock JetBot client for independent Backend & Frontend development."""

import argparse
import asyncio
import contextlib
from datetime import datetime, timezone
import json
import random
from typing import Any, Dict, Optional

import websockets

# Minimal valid 1x1 JPEG image encoded in base64 (for independent event testing).
SAMPLE_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////"
    "////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


async def _command_listener(ws: Any, robot: Dict[str, Any]) -> None:
    """Receive control commands from Backend /ws/robot and update mock state."""
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if msg.get("type") == "heartbeat_ack":
                continue

            cmd = str(msg.get("cmd") or "").strip().lower()
            if not cmd:
                continue

            if cmd == "emergency_stop":
                robot["state"] = "IDLE"
                robot["left"] = 0.0
                robot["right"] = 0.0
                print("[CMD] EMERGENCY_STOP -> Dừng khẩn cấp!")
            elif cmd == "stop":
                robot["state"] = "IDLE"
                robot["left"] = 0.0
                robot["right"] = 0.0
                print("[CMD] STOP -> IDLE")
            elif cmd == "move":
                robot["left"] = msg.get("left", 0.0)
                robot["right"] = msg.get("right", 0.0)
                if robot["state"] == "IDLE":
                    robot["state"] = "TELEOP"
                print(f"[CMD] MOVE left={robot['left']} right={robot['right']}")
            elif cmd == "start_teach":
                robot["state"] = "TEACHING"
                print("[CMD] START_TEACH -> TEACHING")
            elif cmd == "end_teach":
                robot["state"] = "IDLE"
                print("[CMD] END_TEACH -> IDLE")
            elif cmd == "start_patrol":
                robot["state"] = "PATROLLING"
                robot["run_id"] = msg.get("run_id") or robot.get("run_id")
                robot["checkpoint_seq"] = 0
                print(f"[CMD] START_PATROL run_id={robot['run_id']}")
            elif cmd == "pause_patrol":
                robot["state"] = "PAUSED"
                print("[CMD] PAUSE_PATROL -> PAUSED")
            elif cmd == "resume_patrol":
                robot["state"] = "PATROLLING"
                print("[CMD] RESUME_PATROL -> PATROLLING")
    except asyncio.CancelledError:
        raise
    except websockets.ConnectionClosed:
        pass


async def run_mock_robot(
    url: str = "ws://localhost:8000/ws/robot",
    interval: float = 1.0,
    max_ticks: int = 0,
    scenario: str = "patrol",
) -> None:
    """Connect to Backend /ws/robot and emit periodic telemetry, heartbeat, and sample events."""
    print(f"[*] Đang kết nối tới Backend tại {url} (scenario={scenario})...")
    robot: Dict[str, Any] = {
        "state": "PATROLLING",
        "run_id": None,
        "checkpoint_seq": 0,
        "total_checkpoints": 15,
        "battery_v": 12.1 if scenario != "low_battery" else 10.1,
        "left": 0.0,
        "right": 0.0,
    }

    async with websockets.connect(url) as ws:
        print("[+] Mock JetBot đã kết nối! Bắt đầu phát telemetry & sự kiện mẫu...")
        listener_task = asyncio.create_task(_command_listener(ws, robot))
        tick = 0
        try:
            while max_ticks <= 0 or tick < max_ticks:
                tick += 1
                robot["battery_v"] = max(9.6, round(robot["battery_v"] - 0.01, 2))
                battery_pct = int(
                    max(0, min(100, (robot["battery_v"] - 9.6) / (12.6 - 9.6) * 100))
                )

                if robot["state"] == "PATROLLING":
                    robot["checkpoint_seq"] = (robot["checkpoint_seq"] + 1) % robot[
                        "total_checkpoints"
                    ]

                if scenario == "lost" and tick >= 2:
                    match_score = 0.22
                else:
                    match_score = round(random.uniform(0.75, 0.96), 2)

                telemetry = {
                    "type": "telemetry",
                    "state": robot["state"],
                    "run_id": robot["run_id"],
                    "checkpoint_seq": robot["checkpoint_seq"],
                    "total_checkpoints": robot["total_checkpoints"],
                    "match_score": match_score,
                    "battery_v": robot["battery_v"],
                    "battery_pct": battery_pct,
                    "timestamp": _utc_iso(),
                }
                await ws.send(json.dumps(telemetry))

                if tick % 3 == 0:
                    await ws.send(
                        json.dumps({"type": "heartbeat", "timestamp": _utc_iso()})
                    )

                if scenario == "obstacle":
                    if tick == 2:
                        robot["state"] = "BLOCKED"
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "event",
                                    "event_type": "OBSTACLE_BLOCKED",
                                    "confidence": 0.94,
                                    "details": {"zone": "center", "note": "Mock obstacle"},
                                }
                            )
                        )
                        print("[!] Đã gửi OBSTACLE_BLOCKED")
                    elif tick == 4:
                        robot["state"] = "PATROLLING"
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "event",
                                    "event_type": "OBSTACLE_CLEARED",
                                    "confidence": 0.96,
                                    "details": {"note": "Path clear"},
                                }
                            )
                        )
                        print("[!] Đã gửi OBSTACLE_CLEARED")
                elif scenario == "patrol" and (tick == 2 or random.random() < 0.15):
                    event_type = (
                        "PERSON_DETECTED"
                        if tick == 2
                        else random.choice(["PERSON_DETECTED", "OBSTACLE_BLOCKED"])
                    )
                    payload: Dict[str, Any] = {
                        "type": "event",
                        "event_type": event_type,
                        "confidence": round(random.uniform(0.82, 0.98), 2),
                        "details": {"note": "Sự kiện giả lập từ mock_robot.py"},
                    }
                    if event_type == "PERSON_DETECTED":
                        payload["image_base64"] = SAMPLE_JPEG_B64
                    await ws.send(json.dumps(payload))
                    print(f"[!] Đã gửi sự kiện giả lập: {event_type}")

                await asyncio.sleep(interval)
        finally:
            listener_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await listener_task


def main(argv: Optional[list] = None) -> None:
    parser = argparse.ArgumentParser(description="Giả lập JetBot kết nối Backend /ws/robot.")
    parser.add_argument(
        "--url",
        default="ws://localhost:8000/ws/robot",
        help="Địa chỉ WebSocket Backend (mặc định: ws://localhost:8000/ws/robot)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Chu kỳ gửi telemetry tính bằng giây (mặc định: 1.0)",
    )
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=0,
        help="Số tick tối đa trước khi tự dừng, 0 là chạy liên tục (mặc định: 0)",
    )
    parser.add_argument(
        "--scenario",
        choices=["patrol", "obstacle", "low_battery", "lost"],
        default="patrol",
        help="Kịch bản mô phỏng (mặc định: patrol)",
    )
    args = parser.parse_args(argv)

    try:
        asyncio.run(
            run_mock_robot(
                url=args.url,
                interval=args.interval,
                max_ticks=args.max_ticks,
                scenario=args.scenario,
            )
        )
    except KeyboardInterrupt:
        print("[-] Đã dừng Mock Robot.")


if __name__ == "__main__":
    main()
