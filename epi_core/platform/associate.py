"""
EPI File Association — Register .epi as an OS file type.

The embedded viewer lives inside the `.epi` archive, but operating systems do
not execute code from inside a file automatically. Double-click support
therefore requires a registered external handler application.

For Windows, the preferred path is the packaged installer which registers the
installed `epi.exe` system-wide via HKLM. The helper functions in this module
remain useful for pip installs, repair flows, and cross-platform fallback.

    Windows:  HKEY_CURRENT_USER\\Software\\Classes (via winreg)
    macOS:    ~/Library/Application Support/EPI/EPI Viewer.app (Info.plist)
    Linux:    ~/.local/share/mime + ~/.local/share/applications (xdg-mime)

Usage:
    from epi_core.platform.associate import register_file_association
    register_file_association()           # Register .epi file type
    unregister_file_association()         # Clean removal
"""

import os
import shutil
import subprocess
import sys
import tempfile
from importlib import resources
from pathlib import Path
from typing import Optional


# ============================================================
# Windows
# ============================================================

def _resolve_windows_launcher_dir(preferred: Optional[Path] = None) -> Path:
    """Return a writable directory for Windows launcher/registration helper files."""
    candidates: list[Path] = []
    if preferred is not None:
        candidates.append(preferred)
    candidates.extend([
        Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "EPILabs",
        Path(tempfile.gettempdir()) / "EPILabs",
        Path.cwd() / ".epi_associate" / "EPILabs",
        Path.home() / ".epi" / "launcher",
    ])

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".epi_write_probe"
            probe.write_text("ok", encoding="ascii")
            probe.unlink(missing_ok=True)
            return candidate
        except Exception:
            continue

    raise PermissionError("Could not find a writable EPILabs launcher directory")


def _write_windows_script(path: Path, content: str) -> Path:
    """Write Windows script files without a UTF BOM so WSH can execute them.

    In locked-down environments AppData paths can be read-only. In that case,
    fall back to a writable temp location so registration can still proceed.
    """
    target_dir = _resolve_windows_launcher_dir(path.parent)
    target_path = target_dir / path.name
    target_path.write_text(content, encoding="ascii", newline="\r\n")
    return target_path


def _resolve_self_heal_command(python_exe: Optional[Path] = None) -> str:
    """Return the most stable command for login-time self-heal."""
    python_exe = python_exe or Path(sys.executable)

    adjacent_epi = python_exe.parent / "epi.exe"
    if adjacent_epi.exists():
        return f'"{adjacent_epi}" associate --force'

    epi_on_path = shutil.which("epi.exe")
    if epi_on_path:
        return f'"{epi_on_path}" associate --force'

    return f'"{python_exe}" -m epi_core.platform.associate'


def _get_windows_default_icon(python_exe: Optional[Path] = None) -> str:
    """Return the registry value for the Windows `.epi` file icon."""
    python_exe = python_exe or Path(sys.executable)

    icon_candidates = [python_exe.parent / "epi.ico"]
    try:
        packaged_icon = Path(resources.files("epi_core").joinpath("assets", "epi.ico"))
        icon_candidates.append(packaged_icon)
    except Exception:
        pass

    for candidate in icon_candidates:
        if candidate.exists() and candidate.stat().st_size > 0:
            return f'"{candidate.absolute()}"'

    adjacent_epi = python_exe.parent / "epi.exe"
    if adjacent_epi.exists() and adjacent_epi.stat().st_size > 0:
        return f'"{adjacent_epi.absolute()}",0'

    return f'"{python_exe.absolute()}",0'

def _get_epi_launcher_vbs(python_exe: Optional[Path] = None) -> Path:
    """Create and return the path to the VBScript launcher.

    Double-click should prefer the same `epi view "%1"` path the CLI uses.
    That keeps the rendered viewer aligned with the current artifact contents
    and verification context, instead of reopening stale embedded HTML.

    If no usable runtime command is available, the launcher falls back to
    extracting the embedded viewer.html directly from the .epi archive.
    """
    python_exe = python_exe or Path(sys.executable)
    launcher_dir = _resolve_windows_launcher_dir()
    vbs_path = launcher_dir / "launch.vbs"

    adjacent_epi = python_exe.parent / "epi.exe"
    if adjacent_epi.exists() and adjacent_epi.stat().st_size > 0:
        view_command = f'"{adjacent_epi.absolute()}" view "%1"'
    else:
        epi_on_path = shutil.which("epi.exe")
        if epi_on_path:
            view_command = f'"{Path(epi_on_path).absolute()}" view "%1"'
        else:
            pythonw = python_exe.parent / "pythonw.exe"
            if pythonw.exists() and pythonw.stat().st_size > 0:
                view_command = f'"{pythonw.absolute()}" -m epi_cli view "%1"'
            else:
                view_command = f'"{python_exe.absolute()}" -m epi_cli view "%1"'

    escaped_view_command = view_command.replace('"', '""')

    vbs_content = f"""On Error Resume Next
If WScript.Arguments.Count < 1 Then
    WScript.Quit 1
End If

Dim epiPath, zipPath, fso, tempFolder, shell, zipNs, destNs, viewerPath, sh, i, viewerCommand, exitCode
epiPath = WScript.Arguments(0)
Set fso = CreateObject("Scripting.FileSystemObject")
If Not fso.FileExists(epiPath) Then
    WScript.Quit 2
End If
epiPath = fso.GetAbsolutePathName(epiPath)

Set sh = CreateObject("WScript.Shell")
viewerCommand = "{escaped_view_command}"
viewerCommand = Replace(viewerCommand, "%1", Chr(34) & epiPath & Chr(34))
exitCode = sh.Run(viewerCommand, 0, True)
If Err.Number = 0 And exitCode = 0 Then
    WScript.Quit 0
End If
Err.Clear

tempFolder = fso.BuildPath(fso.GetSpecialFolder(2), "epi_view_" & Replace(fso.GetTempName, ".tmp", ""))
If Not fso.FolderExists(tempFolder) Then
    fso.CreateFolder tempFolder
End If

zipPath = fso.BuildPath(tempFolder, "archive.zip")
fso.CopyFile epiPath, zipPath, True

Set shell = CreateObject("Shell.Application")
Set zipNs = shell.NameSpace(zipPath)
If zipNs Is Nothing Then
    WScript.Quit 3
End If
Set destNs = shell.NameSpace(tempFolder)
If destNs Is Nothing Then
    WScript.Quit 5
End If
destNs.CopyHere zipNs.Items(), 16

viewerPath = fso.BuildPath(tempFolder, "viewer.html")
For i = 1 To 200
    If fso.FileExists(viewerPath) Then Exit For
    WScript.Sleep 100
Next
If Not fso.FileExists(viewerPath) Then
    WScript.Quit 4
End If

sh.Run Chr(34) & viewerPath & Chr(34), 1, False
"""
    return _write_windows_script(vbs_path, vbs_content)


def _get_self_heal_vbs(python_exe: Optional[Path] = None) -> Path:
    """Create and return the path to the self-healing VBScript.

    This VBS is added to HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
    so it fires on every Windows login. It re-registers the .epi file association
    if the registry keys are ever deleted (e.g. by Windows Update, system restore,
    antivirus, or registry cleaners).

    Embeds the full path to the Python executable used at registration time, so
    on login the same Python runs re-registration (no reliance on PATH). This
    ensures the fix persists after restart.
    WindowStyle=0 hides the console — completely silent on every login.
    """
    python_exe = python_exe or Path(sys.executable)
    heal_command = _resolve_self_heal_command(python_exe).replace('"', '""')

    launcher_dir = _resolve_windows_launcher_dir()
    vbs_path = launcher_dir / "self_heal.vbs"

    vbs_content = (
        '\'  EPI self-heal: re-registers .epi file association on every login.\r\n'
        '\'  Silent (WindowStyle=0). Safe to run repeatedly (idempotent).\r\n'
        'Dim healCommand\r\n'
        f'healCommand = "{heal_command}"\r\n'
        '\r\n'
        'Dim oShell\r\n'
        'Set oShell = CreateObject("WScript.Shell")\r\n'
        'oShell.Run "cmd /c " & healCommand, 0, False\r\n'
    )
    return _write_windows_script(vbs_path, vbs_content)


def _get_epi_command() -> str:
    """Return the shell open command for .epi files.

    Prefer direct executable/module launches so double-click does not depend on
    Windows Script Host. That keeps the common open path working even on
    locked-down enterprise machines where `.vbs` execution is blocked.
    """
    python_exe = Path(sys.executable)

    adjacent_epi = python_exe.parent / "epi.exe"
    if adjacent_epi.exists() and adjacent_epi.stat().st_size > 0:
        return f'"{adjacent_epi.absolute()}" view "%1"'

    epi_on_path = shutil.which("epi.exe")
    if epi_on_path:
        epi_path = Path(epi_on_path)
        try:
            if epi_path.exists() and epi_path.stat().st_size > 0:
                return f'"{epi_path.absolute()}" view "%1"'
        except Exception:
            pass

    pythonw = python_exe.parent / "pythonw.exe"
    if pythonw.exists() and pythonw.stat().st_size > 0:
        return f'"{pythonw.absolute()}" -m epi_cli view "%1"'

    if python_exe.exists() and python_exe.stat().st_size > 0:
        return f'"{python_exe.absolute()}" -m epi_cli view "%1"'

    return f'"{python_exe.absolute()}" -m epi_cli view "%1"'


def _get_user_open_command() -> str:
    """Return a stable HKCU open command for PyPI/GitHub installs."""
    return _get_epi_command()


def _get_expected_open_command(scope: Optional[str]) -> str:
    """Expected open command by effective association scope."""
    if scope == "HKLM":
        return _get_epi_command()
    return _get_user_open_command()


def _shellexecute_wait(exe: str, params: str, timeout_ms: int = 8000) -> None:
    """Launch exe+params via ShellExecuteExW and wait for the process to finish.

    ShellExecuteExW creates the child process WITHOUT inheriting the calling
    process's MSIX package context.  This is the only way to write to the
    REAL HKCU registry from within a Store Python (MSIX Desktop Bridge) process:

        winreg / ctypes RegCreateKeyEx  → virtualized (per-package store)
        subprocess(['reg', 'add', ...]) → child inherits MSIX context → also virtualized
        ShellExecuteExW                 → new process, NO package context → real HKCU ✓

    Raises RuntimeError if ShellExecuteExW fails to launch.
    """
    import ctypes
    from ctypes import wintypes

    SEE_MASK_NOCLOSEPROCESS = 0x00000040

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize",         wintypes.DWORD),
            ("fMask",          wintypes.ULONG),
            ("hwnd",           wintypes.HWND),
            ("lpVerb",         wintypes.LPCWSTR),
            ("lpFile",         wintypes.LPCWSTR),
            ("lpParameters",   wintypes.LPCWSTR),
            ("lpDirectory",    wintypes.LPCWSTR),
            ("nShow",          ctypes.c_int),
            ("hInstApp",       wintypes.HINSTANCE),
            ("lpIDList",       ctypes.c_void_p),
            ("lpClass",        wintypes.LPCWSTR),
            ("hkeyClass",      wintypes.HKEY),
            ("dwHotKey",       wintypes.DWORD),
            ("hIconOrMonitor", wintypes.HANDLE),
            ("hProcess",       wintypes.HANDLE),
        ]

    sei = SHELLEXECUTEINFOW()
    sei.cbSize     = ctypes.sizeof(SHELLEXECUTEINFOW)
    sei.fMask      = SEE_MASK_NOCLOSEPROCESS
    sei.lpVerb     = "open"
    sei.lpFile     = exe
    sei.lpParameters = params
    sei.nShow      = 0   # SW_HIDE

    shell32 = ctypes.windll.shell32
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    if not shell32.ShellExecuteExW(ctypes.byref(sei)):
        raise RuntimeError(
            f"ShellExecuteExW({exe!r}) failed — error {ctypes.GetLastError()}"
        )

    if sei.hProcess:
        ctypes.windll.kernel32.WaitForSingleObject(sei.hProcess, timeout_ms)
        ctypes.windll.kernel32.CloseHandle(sei.hProcess)


def _run_windows_reg_command(args: list[str], timeout_ms: int = 8000) -> str:
    """Run reg.exe outside packaged/virtualized Python contexts and capture stdout."""
    launcher_dir = _resolve_windows_launcher_dir()

    fd, output_name = tempfile.mkstemp(prefix="reg_", suffix=".txt", dir=launcher_dir)
    os.close(fd)
    output_path = Path(output_name)

    try:
        quoted_args = subprocess.list2cmdline(args)
        cmd_params = f'/c reg {quoted_args} > "{output_path}" 2>&1'
        _shellexecute_wait("cmd.exe", cmd_params, timeout_ms=timeout_ms)
        return output_path.read_text(encoding="utf-8", errors="ignore")
    finally:
        output_path.unlink(missing_ok=True)


def _register_windows_via_reg_add(open_cmd: str, icon_cmd: str) -> None:
    """Fallback: write .epi association using reg add (when regedit didn't work)."""
    commands = [
        ["add", r"HKCU\Software\Classes\.epi", "/ve", "/d", "EPIRecorder.File", "/f"],
        ["add", r"HKCU\Software\Classes\EPIRecorder.File", "/ve", "/d", "EPI Recording File", "/f"],
        ["add", r"HKCU\Software\Classes\EPIRecorder.File\shell\open\command", "/ve", "/d", open_cmd, "/f"],
        ["add", r"HKCU\Software\Classes\EPIRecorder.File\DefaultIcon", "/ve", "/d", icon_cmd, "/f"],
        ["delete", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.epi\UserChoice", "/f"],
    ]

    failures = []
    for args in commands:
        output = _run_windows_reg_command(args, timeout_ms=10000)
        if "The operation completed successfully." not in output:
            if args[0] == "delete" and "unable to find the specified registry key or value" in output.lower():
                continue
            failures.append("reg " + " ".join(args) + f" -> {output.strip()}")

    if failures:
        raise RuntimeError("Windows registry fallback failed:\n" + "\n".join(failures))


def register_windows() -> None:
    """Register .epi file association on Windows via HKCU registry.

    Uses a .reg file imported by regedit.exe launched through ShellExecuteExW.
    If verification shows keys missing, falls back to reg add so association works.

    Raises:
        RuntimeError: if the import fails (before fallback).
    """
    import ctypes

    python_exe = Path(sys.executable)
    open_cmd = _get_user_open_command()
    icon_cmd = _get_windows_default_icon(python_exe)

    # --- Build .reg file ---------------------------------------------------
    # .reg string escaping: backslashes → \\, double-quotes → \"
    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    # Delete UserChoice so our association is the default (no "Open with" override).
    reg_lines = [
        "Windows Registry Editor Version 5.00",
        "",
        "[-HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\FileExts\\.epi\\UserChoice]",
        "",
        "[HKEY_CURRENT_USER\\Software\\Classes\\.epi]",
        '@="EPIRecorder.File"',
        "",
        "[HKEY_CURRENT_USER\\Software\\Classes\\.epi\\OpenWithProgids]",
        '"EPIRecorder.File"=hex(0):',
        "",
        "[HKEY_CURRENT_USER\\Software\\Classes\\EPIRecorder.File]",
        '@="EPI Recording File"',
        "",
        "[HKEY_CURRENT_USER\\Software\\Classes\\EPIRecorder.File\\shell\\open\\command]",
        f'@="{_esc(open_cmd)}"',
        "",
        "[HKEY_CURRENT_USER\\Software\\Classes\\EPIRecorder.File\\DefaultIcon]",
        f'@="{_esc(icon_cmd)}"',
        "",
    ]
    reg_content = "\r\n".join(reg_lines)

    launcher_dir = _resolve_windows_launcher_dir()
    reg_path = launcher_dir / "register.reg"

    # .reg files must be UTF-16 LE with BOM for reliable Windows parsing
    reg_path.write_bytes(b"\xff\xfe" + reg_content.encode("utf-16-le"))

    # --- Import via regedit.exe through ShellExecuteExW --------------------
    # regedit launched via ShellExecuteExW is NOT subject to MSIX virtualisation.
    try:
        _shellexecute_wait("regedit.exe", f'/s "{reg_path.absolute()}"')
    except RuntimeError as e:
        raise RuntimeError(f"regedit.exe import failed: {e}")

    # --- Verify and fallback to reg add if keys are missing -----------------
    # On some systems regedit doesn't write to real HKCU (e.g. terminal/context).
    # Use reg add as fallback so association works for all users.
    try:
        query_output = _run_windows_reg_command(
            ["query", r"HKCU\Software\Classes\.epi", "/ve"],
            timeout_ms=5000,
        )
    except Exception:
        query_output = ""

    verified = "EPIRecorder.File" in query_output

    if not verified:
        # Regedit didn't write visible keys (e.g. wrong context). Fallback: reg add.
        _register_windows_via_reg_add(open_cmd, icon_cmd)
        query_output = _run_windows_reg_command(
            ["query", r"HKCU\Software\Classes\.epi", "/ve"],
            timeout_ms=5000,
        )
        if "EPIRecorder.File" not in query_output:
            raise RuntimeError("Windows registry association could not be verified after fallback registration.")

    # --- Notify Windows shell to refresh file-association cache -------------
    try:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
    except Exception:
        pass


def register_windows_system() -> None:
    """Register .epi file association system-wide via HKLM (requires admin).

    HKLM associations:
    - Apply to ALL users on the machine (not just current user)
    - Cannot be overridden by Windows 10/11 UserChoice
    - Persist across Windows updates and Python reinstalls
    - Behave exactly like Docker and VS Code file associations

    This is called either:
    - By the Inno Setup installer (which requests admin at install time)
    - By `epi associate --system` which re-launches itself elevated via UAC

    Raises:
        PermissionError: if not running as administrator.
        RuntimeError: if registry writes fail.
    """
    import winreg
    import ctypes

    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise PermissionError(
            "HKLM registration requires administrator privileges. "
            "Run: epi associate --system  (triggers UAC prompt)"
        )

    open_cmd = _get_epi_command()
    icon_cmd = _get_windows_default_icon()
    errors = []

    keys = [
        (r"Software\Classes\.epi",                                        "",                   winreg.REG_SZ,  "EPIRecorder.File"),
        (r"Software\Classes\.epi\OpenWithProgids",                        "EPIRecorder.File",   winreg.REG_NONE, b""),
        (r"Software\Classes\EPIRecorder.File",                            "",                   winreg.REG_SZ,  "EPI Recording File"),
        (r"Software\Classes\EPIRecorder.File\shell\open\command",         "",                   winreg.REG_SZ,  open_cmd),
        (r"Software\Classes\EPIRecorder.File\DefaultIcon",                "",                   winreg.REG_SZ,  icon_cmd),
    ]

    for path, name, reg_type, value in keys:
        try:
            with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, name, 0, reg_type, value)
        except Exception as e:
            errors.append(f"HKLM\\{path}: {e}")

    # Register as a capable application (Windows "Default Programs" integration)
    cap_base = r"Software\EPI Labs\EPI Recorder\Capabilities"
    try:
        with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, cap_base, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "ApplicationName", 0, winreg.REG_SZ, "EPI Recorder")
            winreg.SetValueEx(key, "ApplicationDescription", 0, winreg.REG_SZ,
                              "Verifiable execution evidence for AI systems")
        with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, cap_base + r"\FileAssociations", 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, ".epi", 0, winreg.REG_SZ, "EPIRecorder.File")
        with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, r"Software\RegisteredApplications", 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "EPI Recorder", 0, winreg.REG_SZ, cap_base)
    except Exception as e:
        errors.append(f"RegisteredApplications: {e}")

    if errors:
        raise RuntimeError("HKLM registry writes failed:\n" + "\n".join(f"  • {e}" for e in errors))

    # Notify shell
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
    except Exception:
        pass


def _elevate_and_register_system() -> None:
    """Re-launch the current process with admin privileges to write HKLM.

    Uses ShellExecuteW with verb='runas' which triggers the Windows UAC prompt.
    The re-launched process runs `epi associate --system --elevated` which
    calls register_windows_system() with admin rights and exits.

    This is the pip-install equivalent of a proper Windows installer.
    """
    import ctypes
    import re as _re

    # Find epi.exe to elevate — prefer the current installation first so we do
    # not accidentally relaunch a stale PATH entry from another Python.
    epi_exe_path: str | None = None
    candidate = Path(sys.executable).parent / "epi.exe"
    if candidate.exists() and candidate.stat().st_size > 0:
        epi_exe_path = str(candidate)
    if not epi_exe_path:
        found = shutil.which("epi.exe")
        if found and Path(found).stat().st_size > 0:
            epi_exe_path = found
    if not epi_exe_path:
        raise RuntimeError(
            "Cannot find epi.exe for elevation. "
            "Run from an Administrator terminal: epi associate --system"
        )
    epi_exe = epi_exe_path

    # ShellExecuteW with "runas" triggers UAC elevation
    ret = ctypes.windll.shell32.ShellExecuteW(
        None,           # hwnd
        "runas",        # verb — triggers UAC "Do you want to allow..."
        epi_exe,        # file to run (the real epi.exe)
        "associate --system --elevated",  # args — internal flag, skip re-elevation
        None,           # working directory
        1,              # SW_SHOWNORMAL
    )

    if ret <= 32:
        # ShellExecuteW returns > 32 on success, ≤ 32 on error
        raise RuntimeError(
            f"UAC elevation failed (ShellExecuteW returned {ret}). "
            "Try running: epi associate --system  from an Administrator terminal."
        )


def unregister_windows() -> None:
    """Remove .epi file association from Windows registry."""
    import ctypes

    # Use reg.exe for deletes — same reason as register_windows():
    # winreg deletes from Store Python only affect the MSIX virtual store.
    def _reg_delete_tree(key_path: str) -> None:
        subprocess.run(
            ["reg", "delete", f"HKCU\\{key_path}", "/f"],
            capture_output=True,
        )   # Ignore returncode — missing key is fine

    _reg_delete_tree(r"Software\Classes\.epi")
    _reg_delete_tree(r"Software\Classes\EPIRecorder.File")

    # Remove self-heal Run key
    subprocess.run(
        ["reg", "delete",
         r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
         "/v", "EPIRecorder", "/f"],
        capture_output=True,
    )

    # Notify shell
    try:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
    except Exception:
        pass


# ============================================================
# macOS
# ============================================================

def register_macos() -> None:
    """Register .epi file association on macOS via app bundle + lsregister."""
    import plistlib

    # Create a minimal .app bundle
    app_base = (
        Path.home()
        / "Library"
        / "Application Support"
        / "EPI"
        / "EPI Viewer.app"
    )
    contents = app_base / "Contents"
    macos_dir = contents / "MacOS"
    macos_dir.mkdir(parents=True, exist_ok=True)

    # Write Info.plist declaring UTI for .epi
    plist_data = {
        "CFBundleIdentifier": "com.epilabs.viewer",
        "CFBundleName": "EPI Viewer",
        "CFBundleVersion": "1.0",
        "CFBundleExecutable": "epi-open",
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeExtensions": ["epi"],
                "CFBundleTypeName": "EPI Recording File",
                "CFBundleTypeRole": "Viewer",
                "LSHandlerRank": "Owner",
            }
        ],
        "UTExportedTypeDeclarations": [
            {
                "UTTypeIdentifier": "com.epilabs.epi",
                "UTTypeConformsTo": ["public.zip-archive"],
                "UTTypeTagSpecification": {
                    "public.filename-extension": ["epi"]
                },
            }
        ],
    }
    plist_path = contents / "Info.plist"
    with open(plist_path, "wb") as f:
        plistlib.dump(plist_data, f)

    # Create launcher shell script
    exe_path = macos_dir / "epi-open"
    exe_path.write_text('#!/bin/bash\nepi view "$1"\n', encoding="utf-8")
    exe_path.chmod(0o755)

    # Register with Launch Services
    lsregister = (
        "/System/Library/Frameworks/CoreServices.framework"
        "/Versions/A/Frameworks/LaunchServices.framework"
        "/Versions/A/Support/lsregister"
    )
    if Path(lsregister).exists():
        result = subprocess.run(
            [lsregister, "-f", str(app_base)],
            capture_output=True, timeout=10
        )
        # Force LaunchServices database rebuild to avoid propagation delay
        subprocess.run(
            [lsregister, "-kill", "-r", "-domain", "local", "-domain", "user"],
            capture_output=True, timeout=15
        )
    else:
        _register_macos_osascript_fallback()

def _register_macos_osascript_fallback():
    """Fallback for macOS without lsregister (very old systems)."""
    script = '''
    tell application "Finder"
        set epiFile to POSIX file "/tmp/test.epi"
    end tell
    '''
    # Just warn — osascript registration is unreliable
    print("[WARNING] macOS: lsregister not found. Run 'epi associate' after restarting Finder.")


def unregister_macos() -> None:
    """Remove .epi file association from macOS."""
    app_base = (
        Path.home()
        / "Library"
        / "Application Support"
        / "EPI"
        / "EPI Viewer.app"
    )
    if app_base.exists():
        shutil.rmtree(app_base, ignore_errors=True)

    # Unregister from Launch Services
    lsregister = (
        "/System/Library/Frameworks/CoreServices.framework"
        "/Versions/A/Frameworks/LaunchServices.framework"
        "/Versions/A/Support/lsregister"
    )
    if Path(lsregister).exists():
        subprocess.run(
            [lsregister, "-u", str(app_base)],
            capture_output=True,
        )


# ============================================================
# Linux
# ============================================================

def register_linux() -> None:
    """Register .epi file association on Linux via xdg-mime."""
    # 1. Write MIME type definition
    mime_dir = Path.home() / ".local" / "share" / "mime" / "packages"
    mime_dir.mkdir(parents=True, exist_ok=True)
    (mime_dir / "epi-recorder.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">\n'
        '  <mime-type type="application/x-epi-recording">\n'
        '    <comment>EPI Recording File</comment>\n'
        '    <glob pattern="*.epi"/>\n'
        '    <magic priority="50">\n'
        '      <match type="string" offset="0" value="PK"/>\n'
        '    </magic>\n'
        '  </mime-type>\n'
        '</mime-info>\n',
        encoding="utf-8",
    )

    # 2. Write .desktop launcher
    desktop_dir = Path.home() / ".local" / "share" / "applications"
    desktop_dir.mkdir(parents=True, exist_ok=True)
    (desktop_dir / "epi-viewer.desktop").write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=EPI Viewer\n"
        "Exec=epi view %f\n"
        "MimeType=application/x-epi-recording;\n"
        "NoDisplay=true\n",
        encoding="utf-8",
    )

    # 3. Update MIME database and register default handler
    errors = []

    if shutil.which("update-mime-database"):
        mime_base = Path.home() / ".local" / "share" / "mime"
        r = subprocess.run(
            ["update-mime-database", str(mime_base)],
            capture_output=True, timeout=10
        )
        if r.returncode != 0:
            errors.append("update-mime-database failed")
    else:
        errors.append("update-mime-database not found (install: shared-mime-info)")

    if shutil.which("xdg-mime"):
        r = subprocess.run(
            ["xdg-mime", "default", "epi-viewer.desktop", "application/x-epi-recording"],
            capture_output=True, timeout=10
        )
        if r.returncode != 0:
            errors.append("xdg-mime default failed")
    else:
        errors.append("xdg-mime not found (install: xdg-utils)")

    if errors:
        print("[WARNING] Linux file association partially failed:")
        for e in errors:
            print(f"   - {e}")
        print("   Fix with: sudo apt install xdg-utils shared-mime-info")
        print("   Then run: epi associate")


def unregister_linux() -> None:
    """Remove .epi file association from Linux."""
    mime_xml = Path.home() / ".local" / "share" / "mime" / "packages" / "epi-recorder.xml"
    desktop_file = Path.home() / ".local" / "share" / "applications" / "epi-viewer.desktop"

    if mime_xml.exists():
        mime_xml.unlink()
    if desktop_file.exists():
        desktop_file.unlink()

    # Rebuild MIME database
    mime_base = Path.home() / ".local" / "share" / "mime"
    if mime_base.exists():
        subprocess.run(
            ["update-mime-database", str(mime_base)],
            capture_output=True,
        )


# ============================================================
# Unified Entry Points
# ============================================================

import json

_FLAG_PATH = Path.home() / ".epi" / ".filetype_registered"

# Bump when the Windows launcher format changes (e.g. Python-based -> standalone VBS).
# Ensures all users re-register and get the new launcher without needing --force.
_LAUNCHER_VERSION_WIN = 3

def _get_registration_state() -> dict:
    try:
        return json.loads(_FLAG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _set_registration_state():
    """Persist the current registration state so future calls can skip re-registration.

    Stores version, executable, platform, launcher_version, and the exact open
    command so that any change (upgrade, venv switch, launcher format) is detected.
    """
    try:
        _FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "version": _get_epi_version(),
            "executable": sys.executable,
            "platform": sys.platform,
            "open_command": _get_user_open_command() if sys.platform == "win32" else None,
            "launcher_version": _LAUNCHER_VERSION_WIN if sys.platform == "win32" else None,
        }
        _FLAG_PATH.write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass  # Harmless — just means we re-register next run

def _needs_registration() -> bool:
    """
    Return True if (re)registration is needed.

    Four-layer check:
      1. Launcher format upgraded (e.g. v2 = standalone VBS) — re-register so all users get it
      2. Flag file: version or Python exe changed (upgrade, venv switch)
      3. Stored command changed (reinstall, editable install)
      4. OS state: registry/desktop file missing or pointing to a dead path
    """
    try:
        state = _get_registration_state()

        # Layer 0: Windows launcher format upgrade — ensure everyone gets standalone VBS
        if sys.platform == "win32":
            stored_launcher_version = state.get("launcher_version")
            if (
                stored_launcher_version is not None
                and stored_launcher_version < _LAUNCHER_VERSION_WIN
            ):
                return True

        # Layer 1: version or Python interpreter changed
        if (state.get("version") != _get_epi_version() or
                state.get("executable") != sys.executable):
            return True

        # Layer 2: the registered open command has changed
        if sys.platform == "win32":
            stored_cmd = state.get("open_command")
            if stored_cmd != _get_user_open_command():
                return True

        # Layer 3: live OS health check (self-healing)
        return _is_association_broken()
    except Exception:
        return True


def _query_reg_value(root: str, subkey: str, value_name: Optional[str] = None) -> Optional[str]:
    """Read a registry value via reg.exe and return its string payload."""
    try:
        args = ["reg", "query", rf"{root}\{subkey}"]
        if value_name is None:
            args.append("/ve")
        else:
            args.extend(["/v", value_name])
        output = subprocess.run(args, capture_output=True, text=True).stdout
    except Exception:
        return None

    import re as _re
    if "ERROR:" in output:
        return None

    match = _re.search(r"REG_\w+\s+(.+)", output)
    return match.group(1).strip() if match else None


def _get_windows_association_snapshot() -> dict:
    """Return the current Windows association state across HKCU and HKLM."""
    user_choice = _query_reg_value(
        "HKCU",
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.epi\UserChoice",
        "ProgId",
    )

    hkcu_progid = _query_reg_value("HKCU", r"Software\Classes\.epi")
    hklm_progid = _query_reg_value("HKLM", r"Software\Classes\.epi")
    hkcu_cmd = _query_reg_value("HKCU", r"Software\Classes\EPIRecorder.File\shell\open\command")
    hklm_cmd = _query_reg_value("HKLM", r"Software\Classes\EPIRecorder.File\shell\open\command")

    effective_scope = None
    effective_progid = None
    registered_command = None

    if hkcu_progid == "EPIRecorder.File":
        effective_scope = "HKCU"
        effective_progid = hkcu_progid
        registered_command = hkcu_cmd
    elif hklm_progid == "EPIRecorder.File":
        effective_scope = "HKLM"
        effective_progid = hklm_progid
        registered_command = hklm_cmd

    return {
        "user_choice": user_choice,
        "hkcu_progid": hkcu_progid,
        "hklm_progid": hklm_progid,
        "hkcu_command": hkcu_cmd,
        "hklm_command": hklm_cmd,
        "effective_scope": effective_scope,
        "effective_progid": effective_progid,
        "registered_command": registered_command,
    }

def _is_association_broken() -> bool:
    """Perform a live health check on the OS file association."""
    try:
        if sys.platform == "win32":
            snapshot = _get_windows_association_snapshot()
            registered_command = snapshot.get("registered_command")

            if snapshot.get("effective_progid") != "EPIRecorder.File":
                return True

            if not registered_command:
                return True

            expected_cmd = _get_expected_open_command(snapshot.get("effective_scope"))
            if registered_command != expected_cmd:
                return True

            import re as _re
            match = _re.search(r'"([^"]+)"', registered_command)
            if match and not Path(match.group(1)).exists():
                return True

        elif sys.platform == "darwin":
            app_base = Path.home() / "Library/Application Support/EPI/EPI Viewer.app"
            if not app_base.exists():
                return True

        elif sys.platform.startswith("linux"):
            desktop_file = Path.home() / ".local/share/applications/epi-viewer.desktop"
            if not desktop_file.exists():
                return True

        return False
    except Exception:
        return True

def get_association_diagnostics() -> dict:
    """
    Perform a deep diagnostic check of the file association.
    Focuses on Windows 11 'UserChoice' overrides and path validity.
    """
    diag = {"platform": sys.platform, "status": "OK", "issues": []}
    
    if sys.platform == "win32":
        import re as _re
        try:
            snapshot = _get_windows_association_snapshot()
            diag["user_choice"] = snapshot.get("user_choice")
            diag["association_scope"] = snapshot.get("effective_scope")
            diag["registered_command"] = snapshot.get("registered_command")
            diag["extension_progid"] = snapshot.get("effective_progid")
            diag["hkcu_extension_progid"] = snapshot.get("hkcu_progid")
            diag["hklm_extension_progid"] = snapshot.get("hklm_progid")

            prog_id = snapshot.get("user_choice")
            if prog_id and prog_id != "EPIRecorder.File":
                diag["status"] = "OVERRIDDEN"
                diag["issues"].append(
                    f"Windows is forcing '.epi' to open with '{prog_id}' via UserChoice."
                )

            if snapshot.get("effective_progid") != "EPIRecorder.File":
                diag["status"] = "BROKEN"
                diag["issues"].append(
                    r"Registry key '.epi' is not mapped to EPIRecorder.File in HKCU or HKLM."
                )

            cmd = snapshot.get("registered_command")
            if cmd:
                m2 = _re.search(r'"([^"]+)"', cmd)
                if m2 and not Path(m2.group(1)).exists():
                    diag["status"] = "BROKEN"
                    diag["issues"].append(f"Registered executable does not exist: {m2.group(1)}")
                elif cmd != _get_expected_open_command(snapshot.get("effective_scope")):
                    diag["status"] = "BROKEN"
                    diag["issues"].append("Registered open command does not match the current installation.")
            else:
                diag["status"] = "BROKEN"
                diag["issues"].append("Registry key 'EPIRecorder.File' command is missing.")

        except Exception as e:
            diag["status"] = "ERROR"
            diag["issues"].append(f"Diagnostic failed: {e}")

    return diag

def _get_epi_version() -> str:
    try:
        from epi_core import __version__
        return __version__
    except Exception:
        return "unknown"

def _clear_registered() -> None:
    """Remove the registration flag."""
    if _FLAG_PATH.exists():
        try:
            _FLAG_PATH.unlink()
        except PermissionError:
            # Flag cleanup should never be fatal for diagnostics or tests.
            pass


def register_file_association(silent: bool = False, force: bool = False) -> bool:
    """
    Register .epi as an OS file type so double-clicking opens the viewer.

    For Windows, the packaged installer is the preferred path because it writes
    a stable system-wide HKLM association. This function is still valuable for
    pip installs and repair flows.

    Default registration uses user-level settings; the installer and
    `epi associate --system` use HKLM for permanent Windows ownership.
    Idempotent: skips if already registered unless force=True.

    Args:
        silent: If True, never print or raise on failure.
        force: If True, re-register even if flag file exists.

    Returns:
        True if registration was performed, False if skipped or failed.
    """
    if not force and not _needs_registration():
        return False

    try:
        if sys.platform == "win32":
            register_windows()
            diag = get_association_diagnostics()
            if diag.get("status") != "OK" or diag.get("extension_progid") != "EPIRecorder.File":
                issues = diag.get("issues") or []
                issue_text = "; ".join(str(issue) for issue in issues) if issues else "association is still unhealthy after registration"
                raise RuntimeError(f"Post-registration verification failed: {issue_text}")
        elif sys.platform == "darwin":
            register_macos()
        else:
            register_linux()

        _set_registration_state()

        if not silent:
            print("[OK] .epi file association registered successfully.")
            if sys.platform == "darwin":
                print("   If double-click doesn't work yet on macOS, log out and back in, ")
                print("   or run: killall Finder")
        return True

    except Exception as e:
        if not silent:
            print(f"[WARNING] Could not register file association: {e}")
            print("    Run: epi associate   to retry manually")
        return False


def unregister_file_association(silent: bool = False) -> bool:
    """
    Remove .epi file association from the OS.

    Args:
        silent: If True, never print or raise on failure.

    Returns:
        True if unregistration succeeded, False on failure.
    """
    try:
        if sys.platform == "win32":
            unregister_windows()
        elif sys.platform == "darwin":
            unregister_macos()
        else:
            unregister_linux()

        _clear_registered()

        if not silent:
            print("[OK] .epi file association removed.")
        return True

    except Exception as e:
        if not silent:
            print(f"[WARNING] Could not remove file association: {e}")
        return False


if __name__ == "__main__":
    # Called by self_heal.vbs on every Windows login via:
    #   python.exe -m epi_core.platform.associate
    # Silently re-registers .epi if registry keys are missing.
    register_file_association(silent=True)
