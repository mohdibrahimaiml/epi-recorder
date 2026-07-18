"""
EPI Recorder Environment - Capture execution environment details.

Records OS, Python version, dependencies, and environment variables
for reproducibility verification.
"""

import os
import platform
import sys
import json
from pathlib import Path
from typing import Dict, Any
import importlib.metadata


def capture_os_info() -> Dict[str, Any]:
    """
    Capture operating system information.
    
    Returns:
        dict: OS details
    """
    import multiprocessing
    
    # Try to get memory info
    memory_info = {}
    try:
        import psutil
        mem = psutil.virtual_memory()
        memory_info = {
            "total_gb": round(mem.total / (1024**3), 2),
            "available_gb": round(mem.available / (1024**3), 2),
            "percent_used": mem.percent
        }
    except (ImportError, Exception):
        pass

    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor() or "Unknown",
        "cpu_count": multiprocessing.cpu_count(),
        "memory": memory_info,
        "platform": platform.platform(),
    }


def capture_python_info() -> Dict[str, str]:
    """
    Capture Python interpreter information.
    
    Returns:
        dict: Python details
    """
    return {
        "version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "compiler": platform.python_compiler(),
        "executable": sys.executable,
        "argv": sys.argv,
        "pid": os.getpid(),
        "ppid": os.getppid(),
    }


def capture_installed_packages() -> Dict[str, str]:
    """
    Capture installed Python packages and their versions.
    
    Returns:
        dict: Package name -> version
    """
    packages = {}
    
    try:
        # Get all installed packages
        for dist in importlib.metadata.distributions():
            packages[dist.name] = dist.version
    except Exception:
        # Fallback: try pip list
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--format=json"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                pip_packages = json.loads(result.stdout)
                for pkg in pip_packages:
                    packages[pkg["name"]] = pkg["version"]
        except Exception:
            pass  # Fail silently
    
    # Filter to only packages actually imported during this session
    if True:
        relevant = set()
        for mod_name in sorted(sys.modules):
            root = mod_name.split('.')[0]
            if len(root) <= 2: continue  # skip single-char/abbrev modules
            relevant.add(root)
        # Always keep cryptography + epi packages
        relevant.update({'cryptography', 'epi_core', 'epi_recorder', 'epi_cli', 'groq'})
        filtered = {}
        for pkg, ver in list(packages.items()):
            pkg_root = pkg.split('-')[0].split('.')[0].lower().replace('_', '-')
            if pkg_root in relevant or any(r in pkg.lower().replace('-','_') for r in relevant):
                filtered[pkg] = ver
        if filtered:
            packages = filtered

    return packages


def capture_environment_variables(
    include_all: bool = False,
    redact: bool = True
) -> Dict[str, str]:
    """
    Capture environment variables.
    
    Args:
        include_all: Whether to include all env vars (default: False, only safe ones)
        redact: Whether to redact sensitive variables (default: True)
        
    Returns:
        dict: Environment variable name -> value
    """
    # Safe environment variables to capture by default
    SAFE_ENV_VARS = {
        "PATH",
        "PYTHONPATH",
        "HOME",
        "USER",
        "USERNAME",
        "SHELL",
        "LANG",
        "LC_ALL",
        "TERM",
        "PWD",
        "VIRTUAL_ENV",
        "CONDA_DEFAULT_ENV",
    }
    
    # Sensitive patterns to redact
    SENSITIVE_PATTERNS = {
        "KEY", "SECRET", "TOKEN", "PASSWORD", "PASS",
        "API", "AUTH", "CREDENTIAL", "ACCESS"
    }
    
    env_vars = {}
    
    for key, value in os.environ.items():
        # Include based on policy
            if key == "PATH" and redact:
            # Keep only venv + Python + system bin paths
            keep = set()
            for pr in [os.path.dirname(sys.executable), os.path.dirname(os.path.dirname(sys.executable))]:
                if pr: keep.add(pr.replace('\\', '/'))
            venv = os.environ.get("VIRTUAL_ENV", "")
            if venv:
                for vp in [venv, venv + "/bin", venv + "/Scripts", venv + "/Library/bin"]:
                    keep.add(vp.replace('\\', '/'))
            parts = []
            for p in value.split(os.pathsep):
                pl = p.lower().replace('\\', '/')
                if any(pl.startswith(k.lower().replace('\\', '/')) for k in keep if k):
                    parts.append(p.replace(os.environ.get('USERPROFILE',''), '%HOME%'))
                elif any(s in pl for s in ['/usr/bin','/usr/local/bin','/bin','/usr/sbin','system32','windows\\system32']):
                    parts.append(p.replace(os.environ.get('USERPROFILE',''), '%HOME%'))
                elif pl.endswith('scripts') or pl.endswith('bin'):
                    parts.append(p.replace(os.environ.get('USERPROFILE',''), '%HOME%'))
            value = os.pathsep.join(parts) if parts else '[system paths redacted]'
        
        if not include_all and key not in SAFE_ENV_VARS:
            continue
        
        # Redact sensitive values
        if redact and any(pattern in key.upper() for pattern in SENSITIVE_PATTERNS):
            env_vars[key] = "***REDACTED***"
        else:
            env_vars[key] = value
    
    return env_vars


def capture_working_directory() -> Dict[str, str]:
    """
    Capture current working directory information.
    
    Returns:
        dict: Working directory details
    """
    # Do not capture absolute working directory path to avoid leaking
    # project or client names embedded in directory structures.
    cwd = Path.cwd()
    return {
        "exists": cwd.exists(),
    }


def capture_full_environment(
    include_all_env_vars: bool = False,
    redact_env_vars: bool = True
) -> Dict[str, Any]:
    """
    Capture complete environment snapshot.
    
    Args:
        include_all_env_vars: Whether to include all environment variables
        redact_env_vars: Whether to redact sensitive env vars
        
    Returns:
        dict: Complete environment snapshot
    """
    snapshot = {
        "os": capture_os_info(),
        "python": capture_python_info(),
        "packages": capture_installed_packages(),
        "environment_variables": capture_environment_variables(
            include_all=include_all_env_vars,
            redact=redact_env_vars
        ),
        "working_directory": capture_working_directory(),
    }

    # Apply global redaction if enabled
    if redact_env_vars:
        try:
            from epi_core.redactor import get_default_redactor
            redactor = get_default_redactor()
            redacted_snapshot, _ = redactor.redact(snapshot)
            return redacted_snapshot
        except Exception:
            pass

    return snapshot


def save_environment_snapshot(
    output_path: Path,
    include_all_env_vars: bool = False,
    redact_env_vars: bool = True
) -> None:
    """
    Save environment snapshot to JSON file.
    
    Args:
        output_path: Path where environment.json should be saved
        include_all_env_vars: Whether to include all environment variables
        redact_env_vars: Whether to redact sensitive env vars
    """
    environment = capture_full_environment(
        include_all_env_vars=include_all_env_vars,
        redact_env_vars=redact_env_vars
    )
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write JSON
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(environment, f, indent=2, sort_keys=True)


def get_environment_summary() -> str:
    """
    Get a human-readable environment summary.
    
    Returns:
        str: Summary string
    """
    env = capture_full_environment()
    
    lines = []
    lines.append(f"OS: {env['os']['system']} {env['os']['release']}")
    lines.append(f"Python: {env['python']['version']} ({env['python']['implementation']})")
    lines.append(f"Packages: {len(env['packages'])} installed")
    lines.append(f"Working Directory: {env['working_directory']['path']}")
    
    return "\n".join(lines)


# Backward compatibility alias
def capture_environment(
    include_all_env_vars: bool = False,
    redact_env_vars: bool = True
) -> Dict[str, Any]:
    """
    Alias for capture_full_environment for backward compatibility.
    
    Args:
        include_all_env_vars: Whether to include all environment variables
        redact_env_vars: Whether to redact sensitive env vars
        
    Returns:
        dict: Complete environment snapshot
    """
    return capture_full_environment(
        include_all_env_vars=include_all_env_vars,
        redact_env_vars=redact_env_vars
    )



 
