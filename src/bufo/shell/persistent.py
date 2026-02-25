"""Persistent PTY-backed shell with cwd tracking and interrupts."""

from __future__ import annotations

import asyncio
import os
import pty
import re
import signal
from dataclasses import dataclass
from pathlib import Path

_MARKER = "__BUFO_DONE__"
_MARKER_RE = re.compile(r"__BUFO_DONE__(?P<rc>-?\d+)__(?P<pwd>.*)$")


@dataclass(slots=True)
class ShellResult:
    command: str
    output: str
    exit_code: int
    cwd: Path


class PersistentShell:
    def __init__(self, shell_program: str, cwd: Path) -> None:
        self.shell_program = shell_program
        self.cwd = cwd
        self.master_fd: int | None = None
        self.process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self.process is not None:
            return

        master_fd, slave_fd = pty.openpty()
        self.master_fd = master_fd

        self.process = await asyncio.create_subprocess_exec(
            self.shell_program,
            "-i",
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=str(self.cwd),
            preexec_fn=os.setsid,
        )
        os.close(slave_fd)

    async def close(self) -> None:
        if self.process is None:
            return

        if self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=2)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()

        if self.master_fd is not None:
            os.close(self.master_fd)
            self.master_fd = None
        self.process = None

    async def interrupt(self) -> None:
        if self.process is None:
            return
        os.killpg(os.getpgid(self.process.pid), signal.SIGINT)

    async def run(self, command: str, timeout: float | None = None) -> ShellResult:
        if self.process is None or self.master_fd is None:
            raise RuntimeError("Shell not started")

        async with self._lock:
            await self._write(command + "\n")
            await self._write(f'printf "\\n{_MARKER}%s__%s\\n" "$?" "$PWD"\n')
            output, rc, new_cwd = await self._read_until_marker(timeout)
            self.cwd = new_cwd
            return ShellResult(command=command, output=output, exit_code=rc, cwd=self.cwd)

    async def _write(self, text: str) -> None:
        assert self.master_fd is not None
        os.write(self.master_fd, text.encode("utf-8"))

    async def _read_until_marker(self, timeout: float | None) -> tuple[str, int, Path]:
        assert self.master_fd is not None

        chunks: list[str] = []
        buffer = ""

        async def _read_chunk() -> str:
            return await asyncio.to_thread(os.read, self.master_fd, 4096)

        while True:
            raw = await asyncio.wait_for(_read_chunk(), timeout=timeout)
            if not raw:
                raise RuntimeError("Shell process terminated unexpectedly")

            text = raw.decode("utf-8", errors="replace")
            chunks.append(text)
            buffer += text

            lines = buffer.splitlines()
            for line in lines[-6:]:
                match = _MARKER_RE.search(line.strip())
                if not match:
                    continue

                exit_code = int(match.group("rc"))
                cwd = Path(match.group("pwd")).expanduser()
                output = "".join(chunks)
                output = output.replace(line, "")
                return output.strip(), exit_code, cwd

            if len(buffer) > 16000:
                buffer = buffer[-8000:]
