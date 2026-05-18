"""Stdin-based replacement for lerobot's pynput keyboard listener.

WSLg's X server cannot see keys typed in Windows Terminal (a Windows-native
console), so pynput's X11 RECORD listener never fires in that environment.
This module replaces ``lerobot.utils.control_utils.init_keyboard_listener``
with a ``/dev/tty`` + termios cbreak reader that translates the same
escape sequences (right/left arrow, Esc) into the event flags lerobot
expects.

Activated by the companion ``lerobot_keyboard_stdin.pth`` file in
site-packages, which runs ``install_hook()`` at Python startup. The hook
patches ``lerobot.utils.control_utils`` lazily on first import.
"""

from __future__ import annotations

import logging
import os
import select
import sys
import termios
import threading
import tty

_ESC_FOLLOWUP_TIMEOUT_S = 0.05


class _StdinKeyboardListener:
    """Drop-in replacement for pynput's Listener that reads /dev/tty.

    Exposes the same surface lerobot consumes: ``start()`` (no-op idempotent
    after the constructor already started the thread) and ``stop()``.
    """

    def __init__(self, events: dict) -> None:
        self._events = events
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._tty_fd: int | None = None
        self._orig_attrs = None

    def start(self) -> None:
        if self._thread is not None:
            return
        try:
            self._tty_fd = os.open("/dev/tty", os.O_RDONLY | os.O_NOCTTY)
        except OSError as e:
            logging.warning(
                "Stdin keyboard listener: /dev/tty unavailable (%s). "
                "Keyboard control disabled.", e,
            )
            return
        self._orig_attrs = termios.tcgetattr(self._tty_fd)
        tty.setcbreak(self._tty_fd)
        self._thread = threading.Thread(
            target=self._run, name="so101-kbd-stdin", daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._tty_fd is not None and self._orig_attrs is not None:
            try:
                termios.tcsetattr(self._tty_fd, termios.TCSADRAIN, self._orig_attrs)
            except OSError:
                pass
            try:
                os.close(self._tty_fd)
            except OSError:
                pass
            self._tty_fd = None

    def _read_byte(self, timeout: float | None) -> bytes | None:
        fd = self._tty_fd
        if fd is None:
            return None
        try:
            rlist, _, _ = select.select([fd], [], [], timeout)
        except (OSError, ValueError):
            return None
        if not rlist or self._tty_fd is None:
            return None
        try:
            return os.read(fd, 1)
        except OSError:
            return None

    def _run(self) -> None:
        events = self._events
        while not self._stop.is_set():
            ch = self._read_byte(timeout=0.2)
            if ch is None:
                continue
            if ch != b"\x1b":
                continue
            nxt = self._read_byte(timeout=_ESC_FOLLOWUP_TIMEOUT_S)
            if nxt is None:
                print("Escape key pressed. Stopping data recording...", flush=True)
                events["stop_recording"] = True
                events["exit_early"] = True
                continue
            if nxt != b"[":
                continue
            code = self._read_byte(timeout=_ESC_FOLLOWUP_TIMEOUT_S)
            if code == b"C":
                print("Right arrow key pressed. Exiting loop...", flush=True)
                events["exit_early"] = True
            elif code == b"D":
                print(
                    "Left arrow key pressed. Exiting loop and rerecord the last episode...",
                    flush=True,
                )
                events["rerecord_episode"] = True
                events["exit_early"] = True


def init_keyboard_listener_stdin():
    """Replacement for ``lerobot.utils.control_utils.init_keyboard_listener``.

    Returns ``(listener, events)`` with the same shape lerobot expects. When
    stdin is not a TTY (e.g. headless CI runs), returns ``(None, events)``
    matching the original headless fallback.
    """
    events = {
        "exit_early": False,
        "rerecord_episode": False,
        "stop_recording": False,
    }
    if not sys.stdin.isatty():
        logging.warning(
            "Stdin is not a TTY — keyboard control disabled. "
            "Run docker compose with -it (default for `run`).",
        )
        return None, events
    listener = _StdinKeyboardListener(events)
    listener.start()
    return listener, events


def install() -> None:
    """Monkey-patch ``lerobot.utils.control_utils`` with the stdin listener."""
    import lerobot.utils.control_utils as cu

    cu.init_keyboard_listener = init_keyboard_listener_stdin
    cu.is_headless = lambda: False


class _ControlUtilsPatcher:
    """``sys.meta_path`` finder that triggers ``install()`` once
    ``lerobot.utils.control_utils`` finishes loading.

    Re-entrancy guard prevents recursion when we delegate back to the real
    import machinery via ``importlib.util.find_spec``.
    """

    TARGET = "lerobot.utils.control_utils"
    _in_progress = False

    def find_spec(self, fullname, path=None, target=None):
        if fullname != self.TARGET or _ControlUtilsPatcher._in_progress:
            return None
        import importlib.util

        _ControlUtilsPatcher._in_progress = True
        try:
            spec = importlib.util.find_spec(fullname)
        finally:
            _ControlUtilsPatcher._in_progress = False
        if spec is None or spec.loader is None:
            return None
        original_exec_module = spec.loader.exec_module

        def patched_exec_module(module):
            original_exec_module(module)
            try:
                install()
            except Exception:
                import traceback

                traceback.print_exc()

        spec.loader.exec_module = patched_exec_module
        return spec


def install_hook() -> None:
    """Register the meta_path finder. Idempotent."""
    for hook in sys.meta_path:
        if isinstance(hook, _ControlUtilsPatcher):
            return
    sys.meta_path.insert(0, _ControlUtilsPatcher())
