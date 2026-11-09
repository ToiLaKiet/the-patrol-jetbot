from hardware.patroljet import PatrolJet
from hardware.camera import JetCamera

import cv2

robot = PatrolJet("Patrol-01")
camera = JetCamera()

try:
    camera.start()

    frame = camera.get_frame()

    cv2.imwrite("test_camera.jpg", frame)

    print("Camera:", frame.shape)
    print("Robot initialized successfully")

finally:
    robot.stop()
    camera.stop()
