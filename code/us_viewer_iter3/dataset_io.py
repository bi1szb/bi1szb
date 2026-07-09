import re
from pathlib import Path


def numeric_suffix(path: Path) -> int:
    match = re.search(r"-(\d+)\.jpg$", path.name, re.IGNORECASE)
    return int(match.group(1)) if match else 0


def find_sagittal_image(patient_dir: Path):
    sagittal_dir = patient_dir / "us_sagittal"
    if not sagittal_dir.exists():
        return None
    jpgs = sorted(sagittal_dir.glob("*.jpg"), key=lambda p: p.name)
    matches_with_one = [path for path in jpgs if "1" in path.stem]
    if matches_with_one:
        return matches_with_one[0]
    return jpgs[0] if jpgs else None


def find_transverse_images(patient_dir: Path):
    transverse_dir = patient_dir / "us_transverse"
    if not transverse_dir.exists():
        return []
    return sorted(transverse_dir.glob("*.jpg"), key=lambda p: (numeric_suffix(p), p.name))


def find_patient_dirs(dataset_dir: Path):
    patient_dirs = []
    for child in sorted(dataset_dir.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        sagittal = find_sagittal_image(child)
        transverse = find_transverse_images(child)
        if sagittal and transverse:
            patient_dirs.append(child)
    return patient_dirs
