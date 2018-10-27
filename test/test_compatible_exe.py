from __future__ import print_function

import os
import subprocess
import sys
import textwrap

import pytest

from .test_core import julia
from julia.core import _enviorn, which

is_linux = sys.platform.startswith("linux")
is_windows = os.name == "nt"
is_apple = sys.platform == "darwin"


def _get_paths(path):
    return filter(None, path.split(":"))


# Environment variable PYJULIA_TEST_INCOMPATIBLE_PYTHONS is the
# :-separated list of Python executables incompatible with the current
# Python:
incompatible_pythons = _get_paths(os.getenv("PYJULIA_TEST_INCOMPATIBLE_PYTHONS", ""))


try:
    from types import SimpleNamespace
except ImportError:
    from argparse import Namespace as SimpleNamespace


def _run_fallback(args, input=None, **kwargs):
    process = subprocess.Popen(args, stdin=subprocess.PIPE, **kwargs)
    stdout, stderr = process.communicate(input)
    retcode = process.wait()
    return SimpleNamespace(args=args, stdout=stdout, stderr=stderr, returncode=retcode)


try:
    from subprocess import run
except ImportError:
    run = _run_fallback


def runcode(python, code):
    """Run `code` in `python`."""
    return run(
        [python],
        input=textwrap.dedent(code),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=dict(
            _enviorn,
            # Make PyJulia importable:
            PYTHONPATH=os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
        ),
    )


def print_completed_proc(proc):
    # Print output (pytest will hide it by default):
    print("Ran:", *proc.args)
    if proc.stdout:
        print("# --- STDOUT from", *proc.args)
        print(proc.stdout)
    if proc.stderr:
        print("# --- STDERR from", *proc.args)
        print(proc.stderr)
    print("# ---")


def is_dynamically_linked(executable):
    path = which(executable)
    assert os.path.exists(path)
    if is_linux and which("ldd"):
        proc = run(
            ["ldd", path], stdout=subprocess.PIPE, env=_enviorn, universal_newlines=True
        )
        print_completed_proc(proc)
        return "libpython" in proc.stdout
    elif is_apple and which("otool"):
        proc = run(
            ["otool", "-L", path],
            stdout=subprocess.PIPE,
            env=_enviorn,
            universal_newlines=True,
        )
        print_completed_proc(proc)
        return "libpython" in proc.stdout or "/Python" in proc.stdout
    # TODO: support Windows
    return None


@pytest.mark.parametrize("python", incompatible_pythons)
def test_incompatible_python(python):
    if julia.eval("(VERSION.major, VERSION.minor)") == (0, 6):
        # Julia 0.6 implements mixed version
        return

    python = which(python)
    proc = runcode(
        python,
        """
        import os
        from julia import Julia
        Julia(runtime=os.getenv("JULIA_EXE"), debug=True)
        """,
    )
    print_completed_proc(proc)

    assert proc.returncode == 1
    assert "It seems your Julia and PyJulia setup are not supported." in proc.stderr
    dynamic = is_dynamically_linked(python)
    if dynamic is True:
        assert "`libpython` have to match" in proc.stderr
    elif dynamic is False:
        assert "is statically linked to libpython" in proc.stderr