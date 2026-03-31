import asyncio
import subprocess
import sys
from pathlib import Path


LANGUAGE_CONFIG = {
    "python": {
        "extension": ".py",
        "test_extension": "_test.py",
        "run_cmd": [sys.executable],
        "test_cmd": [sys.executable, "-m", "pytest", "-v", "--tb=short", "--no-header"],
        "timeout": 30,
    },
    "javascript": {
        "extension": ".js",
        "test_extension": ".test.js",
        "run_cmd": ["node"],
        "test_cmd": ["node", "--experimental-vm-modules"],
        "timeout": 30,
    },
    "typescript": {
        "extension": ".ts",
        "test_extension": ".test.ts",
        "run_cmd": ["npx", "ts-node"],
        "test_cmd": ["npx", "jest", "--no-coverage"],
        "timeout": 60,
    },
}


def get_config(language: str) -> dict:
    return LANGUAGE_CONFIG.get(language, LANGUAGE_CONFIG["python"])


def write_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


async def run_code(file_path: Path, language: str) -> tuple[bool, str, str]:
    config = get_config(language)
    cmd = config["run_cmd"] + [str(file_path)]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(file_path.parent),
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=config["timeout"]
        )
        success = proc.returncode == 0
        return success, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")
    except asyncio.TimeoutError:
        return False, "", f"Execution timed out after {config['timeout']}s"
    except FileNotFoundError as e:
        return False, "", f"Runtime not found: {e}"


async def run_tests(test_file_path: Path, language: str) -> tuple[bool, str, str]:
    config = get_config(language)

    if language == "python":
        cmd = config["test_cmd"] + [str(test_file_path)]
    else:
        cmd = config["test_cmd"] + [str(test_file_path)]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(test_file_path.parent),
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=config["timeout"]
        )
        success = proc.returncode == 0
        return success, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")
    except asyncio.TimeoutError:
        return False, "", f"Tests timed out after {config['timeout']}s"
    except FileNotFoundError as e:
        return False, "", f"Test runner not found: {e}"


async def check_syntax(file_path: Path, language: str) -> tuple[bool, str]:
    if language == "python":
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "py_compile", str(file_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            return False, stderr.decode("utf-8", errors="replace")
        return True, ""
    elif language in ("javascript", "typescript"):
        proc = await asyncio.create_subprocess_exec(
            "node", "--check", str(file_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            return False, stderr.decode("utf-8", errors="replace")
        return True, ""
    return True, ""
