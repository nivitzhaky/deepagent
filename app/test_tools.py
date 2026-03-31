import asyncio
import sys
from pathlib import Path

import pytest

from tools import check_syntax, get_config, run_code, write_file


TMP = Path(__file__).parent / "_test_tmp"


@pytest.fixture(autouse=True)
def setup_and_teardown():
    import shutil
    TMP.mkdir(exist_ok=True)
    yield
    shutil.rmtree(TMP, ignore_errors=True)


def test_get_config_python():
    cfg = get_config("python")
    assert cfg["extension"] == ".py"
    assert cfg["test_extension"] == "_test.py"


def test_get_config_javascript():
    cfg = get_config("javascript")
    assert cfg["extension"] == ".js"


def test_get_config_fallback():
    cfg = get_config("unknown_lang")
    assert cfg["extension"] == ".py"


def test_write_file():
    path = TMP / "sample.py"
    write_file(path, "x = 1\n")
    assert path.read_text() == "x = 1\n"


def test_check_syntax_valid():
    path = TMP / "valid.py"
    write_file(path, "def add(a, b):\n    return a + b\n")
    ok, err = asyncio.run(check_syntax(path, "python"))
    assert ok is True
    assert err == ""


def test_check_syntax_invalid():
    path = TMP / "invalid.py"
    write_file(path, "def foo(\n")
    ok, err = asyncio.run(check_syntax(path, "python"))
    assert ok is False
    assert len(err) > 0


def test_run_code_success():
    path = TMP / "hello.py"
    write_file(path, "print('hello world')\n")
    success, stdout, stderr = asyncio.run(run_code(path, "python"))
    assert success is True
    assert "hello world" in stdout


def test_run_code_failure():
    path = TMP / "bad.py"
    write_file(path, "raise RuntimeError('boom')\n")
    success, stdout, stderr = asyncio.run(run_code(path, "python"))
    assert success is False
    assert "boom" in stderr
