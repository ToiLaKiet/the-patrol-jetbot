"""Navigation stage entry point; the runtime pipeline is not implemented yet."""


def run(args):
    raise NotImplementedError(
        "Navigation chưa triển khai: inference → chọn subgoal → predict waypoint → "
        "PD controller → (v, omega) → drive(). Chưa khởi tạo camera hoặc motor."
    )
