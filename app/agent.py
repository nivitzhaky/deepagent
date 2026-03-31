import json
import re
import subprocess
import sys
from pathlib import Path

from deepagents import create_deep_agent
from fastapi import WebSocket
from langchain.tools import tool
from langgraph.config import get_stream_writer



SYSTEM_PROMPT = """You are an expert software engineer. Your task is to write correct, tested code.

Follow this EXACT workflow in order:

## 1. Plan
Call `emit_plan` ONCE with a JSON string containing:
  "summary", "approach", "functions" (list of {name, signature, purpose}),
  "test_cases" (list of {description, input, expected}),
  "edge_cases" (list of strings), "implementation_notes"

## 2. Write Implementation
Call `write_solution` with the complete {language} implementation.
- Clean, idiomatic code. No unnecessary comments.
- Handle all edge cases from your plan.

## 3. Write Tests
Call `write_tests` with a complete pytest test file.
- `import` from `solution` (no extension)
- Cover every test case and edge case

## 4. Run Tests
Call `run_tests` to execute the test suite.

## 5. Fix if Needed
If any tests fail, analyse the output, then call `write_solution` with the fix
(and `write_tests` if the tests themselves need correcting).
Call `run_tests` again. Repeat until ALL tests pass.
Stop immediately once all tests pass.

Use ONLY the tools listed above. Do not use any other file or shell tools."""


def _make_tools(session_dir: Path):
    @tool
    def emit_plan(plan_json: str) -> str:
        """Emit the structured implementation plan to the user interface.
        Call exactly once at the start before writing any code.

        Args:
            plan_json: JSON string with keys: summary, approach, functions,
                       test_cases, edge_cases, implementation_notes
        """
        writer = get_stream_writer()
        try:
            plan = json.loads(plan_json)
        except (json.JSONDecodeError, ValueError):
            plan = {"summary": str(plan_json), "functions": [], "test_cases": [], "edge_cases": []}
        writer({"_event": "plan", "data": plan})
        return "Plan displayed to user."

    @tool
    def write_solution(code: str) -> str:
        """Write the implementation code to solution.py on disk.

        Args:
            code: Complete source code for the implementation file.
        """
        (session_dir / "solution.py").write_text(code, encoding="utf-8")
        return "solution.py written successfully."

    @tool
    def write_tests(tests: str) -> str:
        """Write the pytest test file to solution_test.py on disk.

        Args:
            tests: Complete source code for the pytest test file.
        """
        (session_dir / "solution_test.py").write_text(tests, encoding="utf-8")
        return "solution_test.py written successfully."

    @tool
    def run_tests() -> str:
        """Run pytest on solution_test.py and return the full output.
        Returns pass/fail status and detailed output for each test.
        """
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "solution_test.py", "-v", "--tb=short", "--no-header"],
            cwd=str(session_dir),
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout
        if result.stderr.strip():
            output += "\n" + result.stderr
        return output

    return [emit_plan, write_solution, write_tests, run_tests]


def _build_model(model_provider: str, model_name: str):
    if model_provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model_name, temperature=0.2)
    elif model_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model_name, temperature=0.2)
    raise ValueError(f"Unsupported provider: {model_provider}")


class DeepAgent:
    def __init__(
        self,
        websocket: WebSocket,
        session_dir: Path,
        model_provider: str = "openai",
        model_name: str = "gpt-4o",
        max_iterations: int = 10,
    ):
        self.websocket = websocket
        self.session_dir = session_dir
        self.max_iterations = max_iterations
        self.model = _build_model(model_provider, model_name)

    async def emit(self, event_type: str, payload):
        await self.websocket.send_json({"type": event_type, "data": payload})

    async def run(self, assignment: str, language: str):
        await self.emit("start", {"assignment": assignment, "language": language})
        await self.emit("phase", {"phase": "planning", "label": "Planning"})
        await self.emit("log", "Analyzing assignment and creating plan...")

        tools = _make_tools(self.session_dir)
        system_prompt = SYSTEM_PROMPT.replace("{language}", language)

        agent = create_deep_agent(
            model=self.model,
            tools=tools,
            system_prompt=system_prompt,
        )

        task = (
            f"Assignment: {assignment}\n"
            f"Language: {language}\n"
            f"Test framework: pytest\n"
            f"Output files: solution.py and solution_test.py"
        )

        current_code = ""
        current_tests = ""
        iteration = 0
        last_test_output = ""
        last_test_success = False

        try:
            async for chunk in agent.astream(
                {"messages": [{"role": "user", "content": task}]},
                stream_mode=["updates", "messages", "custom"],
            ):
                if isinstance(chunk, tuple):
                    chunk_type, data = chunk
                elif isinstance(chunk, dict):
                    chunk_type = chunk.get("type")
                    data = chunk.get("data")
                else:
                    continue

                if chunk_type == "custom":
                    if isinstance(data, dict) and data.get("_event") == "plan":
                        plan = data["data"]
                        await self.emit("plan", plan)
                        await self.emit("log", f"Plan ready: {plan.get('summary', '')}")
                        await self.emit("phase", {"phase": "building", "label": "Building"})

                elif chunk_type == "messages":
                    try:
                        token, _meta = data
                    except (TypeError, ValueError):
                        continue

                    if hasattr(token, "tool_call_chunks") and token.tool_call_chunks:
                        for tc in token.tool_call_chunks:
                            name = tc.get("name", "")
                            if name == "write_solution":
                                await self.emit("log", "Writing solution.py...")
                            elif name == "write_tests":
                                await self.emit("log", "Writing solution_test.py...")
                            elif name == "run_tests":
                                iteration += 1
                                await self.emit("iteration", {"iteration": iteration, "max": self.max_iterations})
                                await self.emit("log", "Running tests...")

                    if getattr(token, "type", "") == "tool":
                        tool_name = getattr(token, "name", "")
                        content = str(getattr(token, "content", ""))

                        if tool_name in ("write_solution", "write_tests"):
                            code_path = self.session_dir / "solution.py"
                            tests_path = self.session_dir / "solution_test.py"
                            if code_path.exists():
                                current_code = code_path.read_text(encoding="utf-8")
                            if tests_path.exists():
                                current_tests = tests_path.read_text(encoding="utf-8")
                            await self.emit("code_update", {"code": current_code, "tests": current_tests})

                        elif tool_name == "run_tests":
                            last_test_output = content
                            passed = bool(re.search(r"\d+ passed", content))
                            failed = bool(re.search(r"\d+ failed", content))
                            errored = bool(re.search(r"\d+ error", content))
                            last_test_success = passed and not failed and not errored

                            code_path = self.session_dir / "solution.py"
                            tests_path = self.session_dir / "solution_test.py"
                            if code_path.exists():
                                current_code = code_path.read_text(encoding="utf-8")
                            if tests_path.exists():
                                current_tests = tests_path.read_text(encoding="utf-8")

                            await self.emit("code_update", {"code": current_code, "tests": current_tests})
                            await self.emit("test_result", {
                                "success": last_test_success,
                                "output": last_test_output,
                                "iteration": iteration,
                            })

                    elif getattr(token, "type", "") == "ai" and getattr(token, "content", ""):
                        text = token.content if isinstance(token.content, str) else ""
                        if text.strip():
                            await self.emit("reasoning", text[:300])

        except Exception as exc:
            msg = str(exc)
            if "insufficient_quota" in msg or "RateLimitError" in type(exc).__name__:
                friendly = "OpenAI quota exceeded. Check billing at platform.openai.com and update app/.env."
            elif "AuthenticationError" in type(exc).__name__ or "invalid_api_key" in msg:
                friendly = "Invalid OpenAI API key. Update OPENAI_API_KEY in app/.env."
            else:
                friendly = f"Agent error: {msg}"
            await self.emit("error", {"message": friendly})
            return

        code_path = self.session_dir / "solution.py"
        tests_path = self.session_dir / "solution_test.py"
        if code_path.exists():
            current_code = code_path.read_text(encoding="utf-8")
        if tests_path.exists():
            current_tests = tests_path.read_text(encoding="utf-8")

        if last_test_success:
            await self.emit("success", {
                "code": current_code,
                "tests": current_tests,
                "output": last_test_output,
                "iterations": iteration,
                "code_path": str(code_path),
                "test_path": str(tests_path),
            })
        else:
            await self.emit("exhausted", {
                "message": "Agent finished but could not produce passing tests.",
                "last_code": current_code,
                "last_tests": current_tests,
                "last_error": last_test_output,
            })
