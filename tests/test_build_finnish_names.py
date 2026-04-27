import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).parent.parent / "scripts" / "build_finnish_names.py"
DATA_FILE = Path(__file__).parent.parent / "data" / "finnish_names.json"

# Load MALE_NAMES / FEMALE_NAMES once at import time — no side effects because
# build_finnish_names.py guards the write call under `if __name__ == "__main__"`.
_spec = importlib.util.spec_from_file_location("build_finnish_names", _SCRIPT)
_bfn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bfn)
MALE_NAMES: list[str] = _bfn.MALE_NAMES
FEMALE_NAMES: list[str] = _bfn.FEMALE_NAMES


def _run_script():
    subprocess.check_call([sys.executable, str(_SCRIPT)])


def test_data_file_exists_after_run():
    _run_script()
    assert DATA_FILE.exists()


def test_parses_to_list_of_strings():
    _run_script()
    names = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    assert isinstance(names, list)
    assert len(names) >= 50
    assert all(isinstance(n, str) for n in names)


def test_entries_clean_and_unique():
    _run_script()
    names = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    for n in names:
        assert n and n == n.strip(), f"Name has leading/trailing whitespace: {n!r}"
        assert all(c.isalpha() or c == '-' for c in n), \
            f"Name has unexpected characters: {n!r}"
    assert len(names) == len(set(names)), "Names are not unique"


def test_gender_balance():
    _run_script()
    assert len(MALE_NAMES) >= 25
    assert len(FEMALE_NAMES) >= 25
    union = set(MALE_NAMES) | set(FEMALE_NAMES)
    committed = set(json.loads(DATA_FILE.read_text(encoding="utf-8")))
    assert union == committed


def test_deterministic_output():
    _run_script()
    first = DATA_FILE.read_bytes()
    _run_script()
    second = DATA_FILE.read_bytes()
    assert first == second
