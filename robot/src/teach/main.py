"""Teach stage: joystick and the existing JPEG/CSV recorder."""


def run(args):
    print("Teach: joystick + JPEG/CSV. ROSBag và tạo TOPOMAP chưa triển khai.", flush=True)
    from hardware.patroljet import PatrolJet

    robot = PatrolJet("Patrol-01")
    try:
        robot.run_teleop(max_duty=args.max_duty, deadzone=args.deadzone,
                         slew_rate=args.slew_rate, teach_dir=args.teach_dir)
    finally:
        robot.close()
