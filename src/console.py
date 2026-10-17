"""Console output, Windows key input and termination handling."""

import os
import threading
import time
from collections.abc import Callable
from typing import Any

_RESET = "\x1b[0m"


def _say(color: str, tag: str, msg: str) -> None:
    print(f"{color}[{tag}] {msg}{_RESET}", flush=True)


def info(msg: str) -> None:
    _say("\x1b[36m", "INFO", msg)


def ok(msg: str) -> None:
    _say("\x1b[32m", "OK", msg)


def warn(msg: str) -> None:
    _say("\x1b[33m", "WARN", msg)


def error(msg: str) -> None:
    _say("\x1b[31m", "ERROR", msg)


# ------------------------------------------------- termination guard (Windows)

CTRL_C = "\x03"
_interrupted = threading.Event()  # Ctrl+Break
_closing = threading.Event()  # console close / logoff / shutdown
_shutdown_done = threading.Event()  # set once the browser has been closed cleanly
_keepalive: list[Any] = []  # keeps the ctypes callback alive


def setup_console() -> Callable[[], None]:
    """Enable ANSI colors, turn Ctrl+C into a normal key press, block console close.

    Returns a function that restores the original console state.
    """
    import ctypes
    from ctypes import wintypes

    handler_t = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel32.GetStdHandle.restype = wintypes.HANDLE
    kernel32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.GetConsoleWindow.restype = wintypes.HWND
    kernel32.SetConsoleCtrlHandler.argtypes = [handler_t, wintypes.BOOL]

    stdin_h = kernel32.GetStdHandle(-10)
    stdout_h = kernel32.GetStdHandle(-11)
    in_mode, out_mode = wintypes.DWORD(), wintypes.DWORD()
    if not kernel32.GetConsoleMode(stdin_h, ctypes.byref(in_mode)) or not kernel32.GetConsoleMode(
        stdout_h, ctypes.byref(out_mode)
    ):
        raise RuntimeError("Run this tool in an interactive console window.")
    kernel32.SetConsoleMode(stdout_h, out_mode.value | 0x0004)  # VIRTUAL_TERMINAL_PROCESSING
    # Without ENABLE_PROCESSED_INPUT, Ctrl+C is a plain key press and no signal is
    # generated, so neither this process nor Playwright's driver is interrupted.
    kernel32.SetConsoleMode(stdin_h, in_mode.value & ~0x0001)

    def on_ctrl(event: int) -> bool:
        if event in (0, 1):  # CTRL_C_EVENT, CTRL_BREAK_EVENT
            _interrupted.set()
            return True
        if event in (2, 5, 6):  # CLOSE, LOGOFF, SHUTDOWN: the OS kills us a few seconds later
            warn("Console close/logoff requested, closing the browser to save cookies ...")
            _closing.set()
            _shutdown_done.wait(4.0)
            return True
        return False

    callback = handler_t(on_ctrl)
    _keepalive.append(callback)
    kernel32.SetConsoleCtrlHandler(callback, True)

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetSystemMenu.argtypes = [wintypes.HWND, wintypes.BOOL]
    user32.GetSystemMenu.restype = wintypes.HMENU
    user32.DeleteMenu.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT]
    hwnd = kernel32.GetConsoleWindow()
    close_disabled = False
    if os.environ.get("WT_SESSION"):
        warn("Windows Terminal cannot block tab/window close. If it is closed, the tool will")
        warn("still try to close the browser gracefully, but you will not be asked.")
    elif hwnd:
        user32.DeleteMenu(user32.GetSystemMenu(hwnd, False), 0xF060, 0)  # SC_CLOSE
        close_disabled = True
        info("Console close button disabled. Use Ctrl+C to exit.")

    def restore() -> None:
        kernel32.SetConsoleMode(stdin_h, in_mode.value)
        kernel32.SetConsoleMode(stdout_h, out_mode.value)
        if close_disabled:
            user32.GetSystemMenu(hwnd, True)  # revert to the default system menu

    return restore


def poll_key() -> str | None:
    """Non-blocking key read. Returns CTRL_C for Ctrl+C / Ctrl+Break, None if no key."""
    import msvcrt

    if _interrupted.is_set():
        _interrupted.clear()
        return CTRL_C
    if not msvcrt.kbhit():
        return None
    key = msvcrt.getwch()
    if key in ("\x00", "\xe0"):  # arrow/function keys send a second code
        msvcrt.getwch()
        return ""
    return key


def confirm(question: str, default: bool = False) -> bool:
    print(f"\x1b[33m[WARN] {question} [{'Y/n' if default else 'y/N'}] {_RESET}", end="", flush=True)
    answer = False
    while True:
        if _closing.is_set():
            answer = True
            break
        key = poll_key()
        if key is None:
            time.sleep(0.03)
        elif key.lower() in ("y", "n", "\r"):
            answer = default if key == "\r" else key.lower() == "y"
            break
    print("y" if answer else "n")
    _interrupted.clear()
    return answer


def read_line(prompt: str) -> str:
    buf: list[str] = []
    print(prompt, end="", flush=True)
    while True:
        if _closing.is_set():
            raise SystemExit(0)
        key = poll_key()
        if key is None:
            time.sleep(0.03)
        elif key == CTRL_C:
            print()
            if confirm("Exit the tool?"):
                raise SystemExit(0)
            print(prompt + "".join(buf), end="", flush=True)
        elif key in ("\r", "\n"):
            print()
            return "".join(buf).strip()
        elif key == "\b":
            if buf:
                buf.pop()
                print("\b \b", end="", flush=True)
        elif key and key.isprintable():
            buf.append(key)
            print(key, end="", flush=True)


def is_closing() -> bool:
    """True once the console is closing or the system is shutting down."""
    return _closing.is_set()


def mark_shutdown_done() -> None:
    """Tell a pending close handler that the browser has closed cleanly."""
    _shutdown_done.set()
