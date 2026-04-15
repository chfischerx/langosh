"""Python code execution tool — runs in an out-of-process sandbox.

Each call spawns a fresh `python -I -B` subprocess in a private tempdir with:
- scrubbed env (only PATH and PYTHONIOENCODING)
- resource.setrlimit ceilings (memory, CPU, processes, file size, no core)
- wall-clock timeout
- stdout/stderr capped to 64 KB

Set a top-level `result` variable in the code to return a value.
"""

import asyncio
import os
import platform
import shutil
import subprocess
import sys
import tempfile

_OUTPUT_CAP_BYTES = 64 * 1024
_TIMEOUT_SECONDS = 30
_MEMORY_MB = 512
_CPU_SECONDS = 15

_SENTINEL = "__EXECPY_RESULT__:"

_RUNNER_TEMPLATE = """\
import sys
__user_code = sys.stdin.read()
__ns = {{}}
exec(compile(__user_code, '<execute_python>', 'exec'), __ns)
__result = __ns.get('result')
if __result is not None:
    sys.stdout.write({sentinel!r} + repr(__result))
""".format(sentinel=_SENTINEL)


def _preexec_apply_rlimits() -> None:
    """Set resource limits in the child process (Unix only)."""
    if platform.system() == "Windows":
        return
    import resource

    def _set(which, soft):
        try:
            _, hard = resource.getrlimit(which)
            if hard != resource.RLIM_INFINITY:
                soft = min(soft, hard)
            resource.setrlimit(which, (soft, hard))
        except (ValueError, OSError):
            pass

    _set(resource.RLIMIT_AS, _MEMORY_MB * 1024 * 1024)
    _set(resource.RLIMIT_CPU, _CPU_SECONDS)
    _set(resource.RLIMIT_NPROC, 4)
    _set(resource.RLIMIT_FSIZE, 1024 * 1024)
    _set(resource.RLIMIT_CORE, 0)


def _truncate(buf: bytes) -> str:
    if len(buf) <= _OUTPUT_CAP_BYTES:
        return buf.decode("utf-8", errors="replace")
    return buf[:_OUTPUT_CAP_BYTES].decode("utf-8", errors="replace") + "...[truncated]"


def _execute_python_sync(code: str) -> str:
    """Execute Python code in a sandboxed subprocess."""
    sandbox_dir = tempfile.mkdtemp(prefix="execpy-")
    stdout_path = os.path.join(sandbox_dir, ".stdout")
    stderr_path = os.path.join(sandbox_dir, ".stderr")
    try:
        env = {"PATH": "/usr/bin:/bin:" + os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"}
        preexec = _preexec_apply_rlimits if platform.system() != "Windows" else None

        with open(stdout_path, "wb") as out_f, open(stderr_path, "wb") as err_f:
            try:
                proc = subprocess.run(
                    [sys.executable, "-I", "-B", "-c", _RUNNER_TEMPLATE],
                    input=code.encode("utf-8"),
                    cwd=sandbox_dir,
                    env=env,
                    stdout=out_f,
                    stderr=err_f,
                    timeout=_TIMEOUT_SECONDS,
                    preexec_fn=preexec,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return f"Error: timed out after {_TIMEOUT_SECONDS}s"

        with open(stdout_path, "rb") as f:
            stdout = _truncate(f.read(_OUTPUT_CAP_BYTES + 1))
        with open(stderr_path, "rb") as f:
            stderr = _truncate(f.read(_OUTPUT_CAP_BYTES + 1)).strip()

        if proc.returncode != 0:
            return f"Error: subprocess exit {proc.returncode}: {stderr or '<no stderr>'}"

        sentinel_idx = stdout.rfind(_SENTINEL)
        if sentinel_idx >= 0:
            return stdout[sentinel_idx + len(_SENTINEL):]

        # Return stdout if there's any output, otherwise success message
        if stdout.strip():
            return stdout.strip()
        return "Code executed successfully"
    finally:
        shutil.rmtree(sandbox_dir, ignore_errors=True)


EXECUTE_PYTHON = {
    "name": "execute_python",
    "description": "Execute Python code in a sandboxed subprocess. Set a top-level `result` variable to return a value. Stdout is captured and returned.",
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python source code to execute"},
        },
        "required": ["code"],
    },
}


async def execute_python(args: dict) -> str:
    code = args["code"]
    return await asyncio.to_thread(_execute_python_sync, code)


TOOLS = [EXECUTE_PYTHON]
DISPATCH = {"execute_python": execute_python}
