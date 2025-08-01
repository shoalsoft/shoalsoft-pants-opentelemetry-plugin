# Copyright 2019 Pants project contributors (see CONTRIBUTORS.md).
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# NOTE: Vendored from Pants sources to add `chdir` parameter.
# Non-upstreamed changes are:
#   Copyright (C) 2025 Shoal Software LLC. All rights reserved.

from __future__ import annotations

import glob
import os
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
from threading import Thread
from typing import Any, Iterable, Iterator, List, Mapping, TextIO, Union, cast

import pytest
import toml

from pants.base.build_environment import get_buildroot
from pants.base.exiter import PANTS_SUCCEEDED_EXIT_CODE
from pants.option.options_bootstrapper import OptionsBootstrapper
from pants.pantsd.pants_daemon_client import PantsDaemonClient
from pants.util.contextutil import temporary_dir
from pants.util.dirutil import fast_relpath, safe_file_dump, safe_mkdir
from pants.util.osutil import Pid
from pants.util.strutil import ensure_binary

# NB: If `shell=True`, it's a single `str`.
Command = Union[str, List[str]]

# Sometimes we mix strings and bytes as keys and/or values, but in most
# cases we pass strict str->str, and we want both to typecheck.
# TODO: The complexity of this type, and the casting and # type: ignoring we have to do below,
#  is a code smell. We should use bytes everywhere, and convert lazily as needed.
Env = Union[Mapping[str, str], Mapping[bytes, bytes], Mapping[Union[str, bytes], Union[str, bytes]]]


@dataclass(frozen=True)
class PantsResult:
    command: Command
    exit_code: int
    stdout: str
    stderr: str
    workdir: str
    pid: Pid

    def _format_unexpected_error_code_msg(self, msg: str | None) -> str:
        details = [msg] if msg else []
        details.append(" ".join(self.command))
        details.append(f"exit_code: {self.exit_code}")

        def indent(content):
            return "\n\t".join(content.splitlines())

        details.append(f"stdout:\n\t{indent(self.stdout)}")
        details.append(f"stderr:\n\t{indent(self.stderr)}")
        return "\n".join(details)

    def assert_success(self, msg: str | None = None) -> None:
        assert self.exit_code == 0, self._format_unexpected_error_code_msg(msg)

    def assert_failure(self, msg: str | None = None) -> None:
        assert self.exit_code != 0, self._format_unexpected_error_code_msg(msg)


@dataclass(frozen=True)
class PantsJoinHandle:
    command: Command
    process: subprocess.Popen
    workdir: str

    def join(
        self, stdin_data: bytes | str | None = None, stream_output: bool = False
    ) -> PantsResult:
        """Wait for the pants process to complete, and return a PantsResult for
        it."""
        if stdin_data is not None:
            stdin_data = ensure_binary(stdin_data)

        def worker(stream: BytesIO, buffer: bytearray, tee_stream: TextIO) -> None:
            data = stream.read1(1024)
            while data:
                buffer.extend(data)
                tee_stream.write(data.decode(errors="ignore"))
                tee_stream.flush()
                data = stream.read1(1024)

        if stream_output:
            stdout_buffer = bytearray()
            stdout_thread = Thread(
                target=worker, args=(self.process.stdout, stdout_buffer, sys.stdout)
            )
            stdout_thread.daemon = True
            stdout_thread.start()

            stderr_buffer = bytearray()
            stderr_thread = Thread(
                target=worker, args=(self.process.stderr, stderr_buffer, sys.stderr)
            )
            stderr_thread.daemon = True
            stderr_thread.start()

            if stdin_data and self.process.stdin:
                self.process.stdin.write(stdin_data)
            self.process.wait()
            stdout, stderr = (bytes(stdout_buffer), bytes(stderr_buffer))
        else:
            stdout, stderr = self.process.communicate(stdin_data)

        if self.process.returncode != PANTS_SUCCEEDED_EXIT_CODE:
            render_logs(self.workdir)

        return PantsResult(
            command=self.command,
            exit_code=self.process.returncode,
            stdout=stdout.decode(),
            stderr=stderr.decode(),
            workdir=self.workdir,
            pid=self.process.pid,
        )


def run_pants_with_workdir_without_waiting(
    command: Command,
    *,
    pants_exe_args: Iterable[str],
    workdir: str,
    use_pantsd: bool = True,
    config: Mapping | None = None,
    extra_env: Env | None = None,
    shell: bool = False,
    set_pants_ignore: bool = True,
    cwd: str | bytes | os.PathLike | None = None,
) -> PantsJoinHandle:
    args = [
        "--no-pantsrc",
        f"--pants-workdir={workdir}",
    ]
    if set_pants_ignore:
        # FIXME: For some reason, Pants's CI adds the coverage file and it is not ignored by default. Why?
        args.append("--pants-ignore=+['.coverage.*', '.python-build-standalone']")

    pantsd_option_present_in_command = "--no-pantsd" in command or "--pantsd" in command
    pantsd_option_present_in_config = config and "GLOBAL" in config and "pantsd" in config["GLOBAL"]
    if not pantsd_option_present_in_command and not pantsd_option_present_in_config:
        args.append("--pantsd" if use_pantsd else "--no-pantsd")

    # if hermetic:
    #     args.append("--pants-config-files=[]")
    if set_pants_ignore:
        # Certain tests may be invoking `./pants test` for a pytest test with conftest discovery
        # enabled. We should ignore the root conftest.py for these cases.
        args.append("--pants-ignore=+['/conftest.py']")

    # if config:
    #     toml_file_name = os.path.join(workdir, "pants.toml")
    #     with safe_open(toml_file_name, mode="w") as fp:
    #         fp.write(_TomlSerializer(config).serialize())
    #     args.append(f"--pants-config-files={toml_file_name}")

    # The python backend requires setting ICs explicitly.
    # We do this centrally here for convenience.
    # if any("pants.backend.python" in arg for arg in command) and not any(
    #     "--python-interpreter-constraints" in arg for arg in command
    # ):
    #     args.append("--python-interpreter-constraints=['>=3.8,<4']")

    pants_script = list(pants_exe_args)

    # Permit usage of shell=True and string-based commands to allow e.g. `./pants | head`.
    pants_command: Command
    if shell:
        assert not isinstance(command, list), "must pass command as a string when using shell=True"
        pants_command = " ".join([*pants_script, " ".join(args), command])
    else:
        pants_command = [*pants_script, *args, *command]

    # Only allow-listed entries will be included in the environment if hermetic=True. Note that
    # the env will already be fairly hermetic thanks to the v2 engine; this provides an
    # additional layer of hermiticity.
    env: dict[Union[str, bytes], Union[str, bytes]]

    # With an empty environment, we would generally get the true underlying system default
    # encoding, which is unlikely to be what we want (it's generally ASCII, still). So we
    # explicitly set an encoding here.
    env = {"LC_ALL": "en_US.UTF-8"}

    # Apply our allowlist.
    for h in (
        "HOME",
        "PATH",  # Needed to find Python interpreters and other binaries.
    ):
        if value := os.getenv(h):
            env[h] = value

    hermetic_env = os.getenv("HERMETIC_ENV")
    if hermetic_env:
        for h in hermetic_env.strip(",").split(","):
            value = os.getenv(h)
            if value is not None:
                env[h] = value

    env.update(NO_SCIE_WARNING="1", PEX_VENV="true")

    if extra_env:
        env.update(cast(dict[Union[str, bytes], Union[str, bytes]], extra_env))

    # Pants command that was called from the test shouldn't have a parent.
    if "PANTS_PARENT_BUILD_ID" in env:
        del env["PANTS_PARENT_BUILD_ID"]

    print(f"pants_command={pants_command}")
    print(f"env={env}")

    return PantsJoinHandle(
        command=pants_command,
        process=subprocess.Popen(
            pants_command,
            # The type stub for the env argument is unnecessarily restrictive: it requires
            # all keys to be str or all to be bytes. But in practice Popen supports a mix,
            # which is what we pass. So we silence the typechecking error.
            env=env,  # type: ignore
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=shell,
            cwd=cwd,
        ),
        workdir=workdir,
    )


def run_pants_with_workdir(
    command: Command,
    *,
    pants_exe_args: Iterable[str],
    workdir: str,
    use_pantsd: bool = True,
    config: Mapping | None = None,
    extra_env: Env | None = None,
    stdin_data: bytes | str | None = None,
    shell: bool = False,
    set_pants_ignore: bool = True,
    cwd: str | bytes | os.PathLike | None = None,
    stream_output: bool = False,
) -> PantsResult:
    handle = run_pants_with_workdir_without_waiting(
        command,
        pants_exe_args=pants_exe_args,
        workdir=workdir,
        use_pantsd=use_pantsd,
        shell=shell,
        config=config,
        extra_env=extra_env,
        set_pants_ignore=set_pants_ignore,
        cwd=cwd,
    )
    return handle.join(stdin_data=stdin_data, stream_output=stream_output)


def run_pants(
    command: Command,
    *,
    pants_exe_args: Iterable[str],
    use_pantsd: bool = False,
    config: Mapping | None = None,
    extra_env: Env | None = None,
    stdin_data: bytes | str | None = None,
    cwd: str | bytes | os.PathLike | None = None,
    stream_output: bool = False,
) -> PantsResult:
    """Runs Pants in a subprocess.

    :param command: A list of command line arguments coming after `./pants`.
    :param hermetic: If hermetic, your actual `pants.toml` will not be used.
    :param use_pantsd: If True, the Pants process will use pantsd.
    :param config: Optional data for a generated TOML file. A map of <section-name> ->
        map of key -> value.
    :param extra_env: Set these env vars in the Pants process's environment.
    :param stdin_data: Make this data available to be read from the process's stdin.
    """
    with temporary_workdir() as workdir:
        return run_pants_with_workdir(
            command,
            pants_exe_args=pants_exe_args,
            workdir=workdir,
            use_pantsd=use_pantsd,
            config=config,
            stdin_data=stdin_data,
            extra_env=extra_env,
            cwd=cwd,
            stream_output=stream_output,
        )


# -----------------------------------------------------------------------------------------------
# Environment setup.
# -----------------------------------------------------------------------------------------------


@contextmanager
def setup_tmpdir(
    files: Mapping[str, str], raw_files: Mapping[str, bytes] | None = None
) -> Iterator[str]:
    """Create a temporary directory with the given files and return the tmpdir
    (relative to the build root).

    The `files` parameter is a dictionary of file paths to content. All file paths will be prefixed
    with the tmpdir. The file content can use `{tmpdir}` to have it substituted with the actual
    tmpdir via a format string.

    The `raw_files` parameter can be used to write binary files. These
    files will not go through formatting in any way.


    This is useful to set up controlled test environments, such as setting up source files and
    BUILD files.
    """

    raw_files = raw_files or {}

    with temporary_dir(root_dir=get_buildroot()) as tmpdir:
        rel_tmpdir = os.path.relpath(tmpdir, get_buildroot())
        for path, content in files.items():
            safe_file_dump(
                os.path.join(tmpdir, path), content.format(tmpdir=rel_tmpdir), makedirs=True
            )

        for path, data in raw_files.items():
            safe_file_dump(os.path.join(tmpdir, path), data, makedirs=True, mode="wb")

        yield rel_tmpdir


@contextmanager
def temporary_workdir(cleanup: bool = True) -> Iterator[str]:
    # We can hard-code '.pants.d' here because we know that will always be its value
    # in the pantsbuild/pants repo (e.g., that's what we .gitignore in that repo).
    # Grabbing the pants_workdir config would require this pants's config object,
    # which we don't have a reference to here.
    root = os.path.join(get_buildroot(), ".pants.d", "tmp")
    safe_mkdir(root)
    with temporary_dir(root_dir=root, cleanup=cleanup, suffix=".pants.d") as tmpdir:
        yield tmpdir


# -----------------------------------------------------------------------------------------------
# Pantsd and logs.
# -----------------------------------------------------------------------------------------------


def kill_daemon(pid_dir=None):
    args = ["./pants"]
    if pid_dir:
        args.append(f"--pants-subprocessdir={pid_dir}")
    pantsd_client = PantsDaemonClient(
        OptionsBootstrapper.create(env=os.environ, args=args, allow_pantsrc=False).bootstrap_options
    )
    with pantsd_client.lifecycle_lock:
        pantsd_client.terminate()


def ensure_daemon(func):
    """A decorator to assist with running tests with and without the daemon
    enabled."""
    return pytest.mark.parametrize("use_pantsd", [True, False])(func)


def render_logs(workdir: str) -> None:
    """Renders all potentially relevant logs from the given workdir to
    stdout."""
    filenames = list(glob.glob(os.path.join(workdir, "logs/exceptions*log"))) + list(
        glob.glob(os.path.join(workdir, "pants.log"))
    )
    for filename in filenames:
        rel_filename = fast_relpath(filename, workdir)
        print(f"{rel_filename} +++ ")
        for line in _read_log(filename):
            print(f"{rel_filename} >>> {line}")
        print(f"{rel_filename} --- ")


def read_pants_log(workdir: str) -> Iterator[str]:
    """Yields all lines from the pants log under the given workdir."""
    # Surface the pants log for easy viewing via pytest's `-s` (don't capture stdio) option.
    yield from _read_log(f"{workdir}/pants.log")


def _read_log(filename: str) -> Iterator[str]:
    with open(filename) as f:
        for line in f:
            yield line.rstrip()


@dataclass(frozen=True)
class _TomlSerializer:
    """Convert a dictionary of option scopes -> Python values into TOML
    understood by Pants.

    The constructor expects a dictionary of option scopes to their corresponding values as
    represented in Python. For example:

      {
        "GLOBAL": {
          "o1": True,
          "o2": "hello",
          "o3": [0, 1, 2],
        },
        "some-subsystem": {
          "dict_option": {
            "a": 0,
            "b": 0,
          },
        },
      }
    """

    parsed: Mapping[str, dict[str, int | float | str | bool | list | dict]]

    def normalize(self) -> dict:
        def normalize_section_value(option, option_value) -> tuple[str, Any]:
            # With TOML, we store dict values as strings (for now).
            if isinstance(option_value, dict):
                option_value = str(option_value)
            if option.endswith(".add"):
                option = option.rsplit(".", 1)[0]
                option_value = f"+{option_value!r}"
            elif option.endswith(".remove"):
                option = option.rsplit(".", 1)[0]
                option_value = f"-{option_value!r}"
            return option, option_value

        return {
            section: dict(
                normalize_section_value(option, option_value)
                for option, option_value in section_values.items()
            )
            for section, section_values in self.parsed.items()
        }

    def serialize(self) -> str:
        toml_values = self.normalize()
        return toml.dumps(toml_values)
