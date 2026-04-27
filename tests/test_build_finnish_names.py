import json
import subprocess
import sys
from pathlib import Path

DATA_FILE = Path(__file__).parent.parent / "data" / "finnish_names.json"


def _run_script():
    script = Path(__file__).parent.parent / "scripts" / "build_finnish_names.py"
    subprocess.check_call([sys.executable, str(script)])


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
    import importlib.util
    script = Path(__file__).parent.parent / "scripts" / "build_finnish_names.py"
    spec = importlib.util.spec_from_file_location("bfn", str(script))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "MALE_NAMES") and hasattr(mod, "FEMALE_NAMES")
    assert len(mod.MALE_NAMES) >= 25
    assert len(mod.FEMALE_NAMES) >= 25
    union = set(mod.MALE_NAMES) | set(mod.FEMALE_NAMES)
    committed = set(json.loads(DATA_FILE.read_text(encoding="utf-8")))
    assert union == committed


def test_deterministic_output():
    _run_script()
    first = DATA_FILE.read_bytes()
    _run_script()
    second = DATA_FILE.read_bytes()
    assert first == second
