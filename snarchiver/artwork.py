import logging
import pathlib
import shutil
import subprocess
import tempfile

logger = logging.getLogger(__name__)

MIN_DIMENSION = 300
MAX_ASPECT = 3.0
_ACCEPTED_SUFFIXES = (".jpg", ".jpeg", ".png")


def have_pdfimages() -> bool:
    return shutil.which("pdfimages") is not None


def acceptable(width: int, height: int) -> bool:
    if width <= 0 or height <= 0:
        return False
    if min(width, height) < MIN_DIMENSION:
        return False
    return max(width, height) / min(width, height) <= MAX_ASPECT


def _page_one_size(pdf_path) -> tuple[int, int] | None:
    try:
        result = subprocess.run(
            ["pdfimages", "-list", "-f", "1", "-l", "1", str(pdf_path)],
            capture_output=True, text=True, check=False, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in result.stdout.splitlines()[2:]:
        parts = line.split()
        if len(parts) > 4:
            try:
                return int(parts[3]), int(parts[4])
            except ValueError:
                continue  # this row is malformed; a later row may still be usable
    return None


def extract_cover(pdf_path, dest) -> bool:
    """Page-1 image from a notes PDF, or False if there isn't a usable one."""
    size = _page_one_size(pdf_path)
    if not size or not acceptable(*size):
        return False

    dest = pathlib.Path(dest)
    staged = dest.with_name(dest.name + ".part")
    with tempfile.TemporaryDirectory() as work:
        prefix = pathlib.Path(work) / "img"
        try:
            subprocess.run(["pdfimages", "-j", "-f", "1", "-l", "1",
                            str(pdf_path), str(prefix)],
                           capture_output=True, check=False, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            return False
        try:
            for candidate in sorted(pathlib.Path(work).iterdir()):
                if candidate.suffix.lower() in _ACCEPTED_SUFFIXES:
                    shutil.copy2(str(candidate), staged)
                    staged.replace(dest)
                    return True
        except OSError:
            try:
                staged.unlink(missing_ok=True)
            except OSError:
                pass
            return False
    return False
