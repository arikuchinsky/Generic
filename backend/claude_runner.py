import asyncio
import json
import signal
import os
from typing import AsyncGenerator, Optional


class ClaudeRunner:
    def __init__(self):
        self._process: Optional[asyncio.subprocess.Process] = None

    async def run(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        model: str = "sonnet",
        working_dir: str = ".",
        auto_approve: bool = True,
        resume_session: Optional[str] = None,
    ) -> AsyncGenerator[dict, None]:
        cmd = [
            "claude",
            "-p", prompt,
            "--output-format", "stream-json",
            "--verbose",
        ]

        if model:
            cmd.extend(["--model", model])

        if resume_session:
            cmd.extend(["--resume", resume_session])

        if auto_approve:
            cmd.extend(["--allowedTools", "Edit", "Write", "Read", "Bash",
                        "Glob", "Grep", "WebSearch", "WebFetch", "Agent",
                        "NotebookEdit", "TodoWrite"])

        env = os.environ.copy()

        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
            env=env,
        )

        buffer = ""
        try:
            while True:
                chunk = await self._process.stdout.read(4096)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="replace")

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        yield event
                    except json.JSONDecodeError:
                        yield {"type": "raw", "data": {"text": line}}

            await self._process.wait()

            stderr_output = await self._process.stderr.read()
            if self._process.returncode != 0 and stderr_output:
                yield {
                    "type": "error",
                    "data": {
                        "message": stderr_output.decode("utf-8", errors="replace"),
                        "code": self._process.returncode,
                    },
                }
        except asyncio.CancelledError:
            await self.cancel()
            raise
        finally:
            self._process = None

    async def cancel(self):
        if self._process and self._process.returncode is None:
            try:
                self._process.send_signal(signal.SIGTERM)
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
            except ProcessLookupError:
                pass
