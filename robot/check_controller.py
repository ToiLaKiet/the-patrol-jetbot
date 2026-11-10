"""Print USB controller events without importing or commanding the robot."""

import os

# TGZ detection on this Jetson requires the classic Linux joystick interface.
os.environ["SDL_LINUX_JOYSTICK_CLASSIC"] = "1"
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"

import pygame


def main():
    try:
        pygame.display.init()
        pygame.joystick.init()
        if pygame.joystick.get_count() == 0:
            raise RuntimeError("Không tìm thấy tay cầm USB")

        controller = pygame.joystick.Joystick(0)
        controller.init()
        instance_id = controller.get_instance_id()
        print("Tên:", controller.get_name())
        print("Axes:", controller.get_numaxes())
        print("Buttons:", controller.get_numbuttons())
        print("Đẩy cần trái lên, sang phải, rồi nhấn/thả L1. Ctrl+C để thoát.")

        clock = pygame.time.Clock()
        while True:
            for event in pygame.event.get():
                if getattr(event, "instance_id", None) != instance_id:
                    continue
                if event.type == pygame.JOYDEVICEREMOVED:
                    raise RuntimeError("Tay cầm đã ngắt kết nối")
                if event.type == pygame.JOYAXISMOTION:
                    print(f"Axis {event.axis}: {event.value:+.2f}")
                elif event.type == pygame.JOYBUTTONDOWN:
                    print(f"Button {event.button}: NHẤN")
                elif event.type == pygame.JOYBUTTONUP:
                    print(f"Button {event.button}: THẢ")
                elif event.type == pygame.JOYHATMOTION:
                    print(f"D-pad {event.hat}: {event.value}")
            clock.tick(30)
    except KeyboardInterrupt:
        print("Đã dừng kiểm tra.")
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
