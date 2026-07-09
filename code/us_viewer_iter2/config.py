import re


DEFAULT_SCALE_NUMERATOR = 790.0
HANDLE_RADIUS = 7
MAJOR_TICK_UNITS = 10


def parse_depth_and_scale(input_text: str):
    parts = [part.strip() for part in re.split(r"[,，\s]+", input_text.strip()) if part.strip()]
    if not parts:
        raise ValueError("depth cannot be empty")
    depth = float(parts[0])
    if depth <= 0:
        raise ValueError("depth must be greater than 0")
    numerator = float(parts[1]) if len(parts) > 1 else DEFAULT_SCALE_NUMERATOR
    if numerator <= 0:
        raise ValueError("scale numerator must be greater than 0")
    return depth, numerator, numerator / depth
