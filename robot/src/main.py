from hardware.patroljet import PatrolJet


def main():
    robot = PatrolJet("Patrol-01")
    try:
        robot.run_teleop(max_speed=0.25)
    finally:
        robot.close()


if __name__ == "__main__":
    main()
