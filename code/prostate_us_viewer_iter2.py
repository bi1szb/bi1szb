import sys
from pathlib import Path

from PyQt5.QtWidgets import QApplication

from us_viewer_iter2.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    workspace_root = Path(__file__).resolve().parent.parent
    default_candidates = [
        workspace_root / "data" / "jpg",
        Path.cwd() / "data" / "jpg",
        Path.cwd() / "dataset",
        workspace_root / "dataset",
    ]
    for default_dataset in default_candidates:
        if default_dataset.exists():
            window.open_dataset(default_dataset)
            break
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
