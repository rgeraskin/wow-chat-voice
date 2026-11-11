"""Starting WoW through Battle.net, and telling whether it still runs (Windows only)."""
from __future__ import annotations

import ctypes
import os
import subprocess
from ctypes import wintypes
from pathlib import Path

TH32CS_SNAPPROCESS = 0x2


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]


def process_names() -> set[str]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    names = set()
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            names.add(entry.szExeFile.lower())
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return names


def wow_running() -> bool:
    return any(n.startswith("wow") and n.endswith(".exe") and "voice" not in n for n in process_names())


def find_battlenet(config: dict) -> Path | None:
    if config.get("battlenet_exe"):
        path = Path(config["battlenet_exe"])
        return path if path.exists() else None
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Battle.net")
        location, _ = winreg.QueryValueEx(key, "InstallLocation")
        path = Path(location) / "Battle.net.exe"
        if path.exists():
            return path
    except OSError:
        pass
    for base in (os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), r"C:\Program Files", "D:\\", "E:\\"):
        path = Path(base) / "Battle.net" / "Battle.net.exe"
        if path.exists():
            return path
    return None


def launch(config: dict, log) -> bool:
    """Ask Battle.net to start the game (`launch_product`: WoWF is Forever, WoW retail)."""
    exe = find_battlenet(config)
    if exe is None:
        log("Battle.net не найден: запустите игру сами (или укажите battlenet_exe в config.json)")
        return False
    product = config.get("launch_product", "WoWF")
    subprocess.Popen([str(exe), f"--exec=launch {product}"], close_fds=True,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    log(f"запускаю игру через Battle.net ({product}) ...")
    return True
