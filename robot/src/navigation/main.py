"""Navigation stage entry point; the runtime pipeline is not implemented yet."""

import argparse


def main(argv=None):
    parser = argparse.ArgumentParser(description="Navigation theo PlaceNav (chưa triển khai).")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except NotImplementedError as error:
        parser.error(str(error))


def run(args):
    raise NotImplementedError(
        "Navigation chưa triển khai: inference → chọn subgoal → predict waypoint → "
        "PD controller → (v, omega) → drive(). Chưa khởi tạo camera hoặc motor."
    )


if __name__ == "__main__":
    main()
