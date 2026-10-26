#!/usr/bin/env python3
"""Seed-free pip bootstrap for reviewed Linux controllers; no system-store writes."""
from __future__ import annotations

import argparse
import contextlib
import email.parser
import hashlib
import importlib.metadata
import io
import json
import os
import platform
import runpy
import ssl
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import venv
import zipfile
from pathlib import Path

PIP_VERSION = "26.2.2"
PIP_SHA256 = "fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70"  # pragma: allowlist secret
PIP_WHEEL = f"pip-{PIP_VERSION}-py3-none-any.whl"
PIP_URL = (
    "https://files.pythonhosted.org/packages/3f/06/"
    "3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/"
    + PIP_WHEEL
)
CA_SHA256 = "50f79f98dac192b20dbf73f35c56f0b0c557ab267ff5199d1117cc1180b70785"  # pragma: allowlist secret
DENIED_ROOT = "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b"  # pragma: allowlist secret
CA_FILE = Path(__file__).resolve().parent / "bootstrap" / "cacert.crt"
MAX_WHEEL_BYTES = 8 * 1024 * 1024


class BootstrapError(ValueError):
    """The approved bootstrap could not be established; never fall back."""


def _read_regular(path: Path, limit: int = MAX_WHEEL_BYTES) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        with os.fdopen(os.open(path, flags), "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise BootstrapError("Bootstrap input must be a regular file")
            data = stream.read(limit + 1)
    except OSError as error:
        raise BootstrapError(f"Cannot read bootstrap input: {path}") from error
    if len(data) > limit:
        raise BootstrapError("Bootstrap input exceeds its size limit")
    return data


def approved_ca() -> bytes:
    data = _read_regular(CA_FILE)
    if hashlib.sha256(data).hexdigest() != CA_SHA256:
        raise BootstrapError("Unapproved bootstrap CA bundle")
    return data


def tls_context() -> ssl.SSLContext:
    # Explicit cadata avoids loading default cafile/capath or environment roots.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cadata=approved_ca().decode("ascii"))
    roots = {hashlib.sha256(cert).hexdigest()
             for cert in context.get_ca_certs(binary_form=True)}
    if DENIED_ROOT in roots or not roots:
        raise BootstrapError("Unacceptable bootstrap trust anchors")
    return context


def verify_wheel(data: bytes, expected_hash: str = PIP_SHA256,
                 expected_version: str = PIP_VERSION) -> bytes:
    if expected_hash != PIP_SHA256 or expected_version != PIP_VERSION:
        raise BootstrapError("Only the reviewed pip version and hash are allowed")
    if len(data) > MAX_WHEEL_BYTES or hashlib.sha256(data).hexdigest() != expected_hash:
        raise BootstrapError("Pip wheel SHA-256 mismatch")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            metadata = email.parser.BytesParser().parsebytes(
                archive.read(f"pip-{PIP_VERSION}.dist-info/METADATA")
            )
    except (KeyError, ValueError, zipfile.BadZipFile) as error:
        raise BootstrapError("Invalid pip wheel metadata") from error
    if metadata["Name"] != "pip" or metadata["Version"] != PIP_VERSION:
        raise BootstrapError("Unexpected pip wheel version")
    return data


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BootstrapError("Bootstrap redirects are not allowed")


def fetch_wheel(output: Path) -> Path:
    if output.exists() or output.is_symlink():
        verify_wheel(_read_regular(output))
        return output
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _NoRedirect(),
        urllib.request.HTTPSHandler(context=tls_context()),
    )
    try:
        with opener.open(PIP_URL, timeout=30) as response:
            if response.geturl() != PIP_URL or response.status != 200:
                raise BootstrapError("Unexpected bootstrap response")
            data = verify_wheel(response.read(MAX_WHEEL_BYTES + 1))
    except (OSError, urllib.error.URLError) as error:
        raise BootstrapError("Verified bootstrap download unavailable") from error
    # Publish only verified bytes, without replacing a concurrently created file.
    try:
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        verify_wheel(_read_regular(output))
    else:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
    return output


@contextlib.contextmanager
def staged_wheel(path: Path):
    # Never import from the caller's mutable original after validating its bytes.
    data = verify_wheel(_read_regular(path))
    with tempfile.TemporaryDirectory(prefix="hardenops-pip-") as directory:
        staged = Path(directory) / PIP_WHEEL
        with os.fdopen(os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
                       "wb") as stream:
            stream.write(data)
        yield staged


def _offline_guard(event: str, args) -> None:
    if event.startswith("socket.") or event in {
        "subprocess.Popen", "os.system", "os.posix_spawn", "os.posix_spawnp",
        "os.exec", "os.fork", "os.forkpty",
    }:
        raise PermissionError(f"Offline pip bootstrap denied {event}")


def _offline_install(wheel: Path) -> None:
    sys.addaudithook(_offline_guard)
    if sys.prefix == sys.base_prefix:
        raise BootstrapError("Refusing to modify a base/system Python")
    verify_wheel(_read_regular(wheel))
    for key in list(os.environ):
        if key.startswith("PIP_"):
            del os.environ[key]
    os.environ.update(PIP_CONFIG_FILE=os.devnull, PIP_NO_INDEX="1",
                      PIP_DISABLE_PIP_VERSION_CHECK="1")
    with tempfile.TemporaryDirectory(prefix="hardenops-pip-requirements-") as directory:
        requirements = Path(directory) / "pip.txt"
        requirements.write_text(f"{wheel.as_uri()} --hash=sha256:{PIP_SHA256}\n")
        sys.path.insert(0, str(wheel))
        sys.argv = ["pip", "--disable-pip-version-check", "--no-cache-dir", "install",
                    "--no-index", "--no-deps", "--require-hashes", "--only-binary=:all:",
                    "--force-reinstall", "-r", str(requirements)]
        runpy.run_module("pip", run_name="__main__")


def install_pip(python: Path, wheel: Path) -> None:
    with staged_wheel(wheel) as staged:
        command = [str(python), "-I", "-B", str(Path(__file__).resolve()),
                   "_offline-install", "--wheel", str(staged)]
        try:
            subprocess.run(command, check=True, stdout=sys.stderr)
        except (OSError, subprocess.CalledProcessError) as error:
            raise BootstrapError("Offline pip installation failed") from error
    result = subprocess.check_output([
        str(python), "-I", "-B", "-c",
        ("import importlib.metadata as m,sys; "
         "assert sys.prefix != sys.base_prefix; print(m.version('pip'))"),
    ], text=True).strip()
    if result != PIP_VERSION:
        raise BootstrapError("Bootstrap did not install the reviewed pip")


def _trust_files(directory: Path) -> dict[str, str]:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink():
        raise BootstrapError("Trust directory cannot be a symlink")
    info = directory.stat()
    if info.st_uid != os.geteuid() or info.st_mode & 0o022:
        raise BootstrapError("Trust directory must be privately controlled")
    cafile = directory / "cacert.pem"
    if cafile.exists() or cafile.is_symlink():
        if _read_regular(cafile) != approved_ca():
            raise BootstrapError("Existing trust snapshot is not approved")
    else:
        with os.fdopen(os.open(cafile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
                       "wb") as stream:
            stream.write(approved_ca())
    capath = directory / "empty"
    capath.mkdir(mode=0o700, exist_ok=True)
    if capath.is_symlink() or any(capath.iterdir()):
        raise BootstrapError("Bootstrap capath must be an owned empty directory")
    info = capath.stat()
    if info.st_uid != os.geteuid() or info.st_mode & 0o022:
        raise BootstrapError("Bootstrap capath must be privately controlled")
    return {"SSL_CERT_FILE": str(cafile), "SSL_CERT_DIR": str(capath),
            "PIP_CERT": str(cafile), "REQUESTS_CA_BUNDLE": str(cafile),
            "PIP_CONFIG_FILE": os.devnull, "PIP_DISABLE_PIP_VERSION_CHECK": "1"}


@contextlib.contextmanager
def trusted_environment():
    previous = os.environ.copy()
    with tempfile.TemporaryDirectory(prefix="hardenops-trust-") as directory:
        try:
            for key in list(os.environ):
                if (key.startswith("PIP_") and not key.startswith("PIP_AUDIT_")) or key in {
                    "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
                }:
                    del os.environ[key]
            os.environ.update(_trust_files(Path(directory)))
            yield
        finally:
            os.environ.clear()
            os.environ.update(previous)


def prepare(destination: Path, wheel: Path, github_env: Path | None = None,
            github_path: Path | None = None) -> None:
    if (sys.platform != "linux" or platform.machine() not in {"x86_64", "amd64"}
            or platform.python_implementation() != "CPython"):
        raise BootstrapError("Supported bootstrap: CPython on Linux x86_64")
    if sys.version_info[:2] not in {(3, 12), (3, 13)}:
        raise BootstrapError("Supported bootstrap: CPython 3.12 or 3.13")
    verify_wheel(_read_regular(wheel))
    if destination.is_symlink():
        raise BootstrapError("Environment directory cannot be a symlink")
    if not destination.exists():
        destination.mkdir(mode=0o700, parents=True)
        venv.EnvBuilder(with_pip=False).create(destination)
    elif not (destination / "pyvenv.cfg").is_file():
        raise BootstrapError("Refusing to overwrite a non-venv directory")
    info = destination.stat()
    if info.st_uid != os.geteuid() or info.st_mode & 0o022:
        raise BootstrapError("Environment must be privately controlled")
    install_pip(destination / "bin/python", wheel)
    values = _trust_files(destination / ".hardenops-bootstrap")
    values["HARDENOPS_PIP_WHEEL"] = str(wheel.resolve())
    if any("\n" in value or "\r" in value for value in values.values()):
        raise BootstrapError("Invalid job environment path")
    if github_env:
        with github_env.open("a") as stream:
            stream.writelines(f"{key}={value}\n" for key, value in values.items())
    if github_path:
        with github_path.open("a") as stream:
            stream.write(str(destination.resolve() / "bin") + "\n")
    print(json.dumps({"pip": PIP_VERSION, "venv": str(destination), "trust": values}))


def default_wheel() -> Path:
    explicit = os.environ.get("HARDENOPS_PIP_WHEEL")
    if explicit:
        return Path(explicit)
    base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return base / "hardenops-bootstrap" / PIP_WHEEL


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("fetch")
    fetch.add_argument("--output", type=Path, default=default_wheel())
    verify = commands.add_parser("verify")
    verify.add_argument("--wheel", type=Path, required=True)
    verify.add_argument("--sha256", default=PIP_SHA256)
    verify.add_argument("--version", default=PIP_VERSION)
    seed = commands.add_parser("seed")
    seed.add_argument("--wheel", type=Path, default=default_wheel())
    create = commands.add_parser("prepare")
    create.add_argument("--venv", type=Path, required=True)
    create.add_argument("--wheel", type=Path, default=default_wheel())
    create.add_argument("--github-env", type=Path)
    create.add_argument("--github-path", type=Path)
    execute = commands.add_parser("run")
    execute.add_argument("arguments", nargs=argparse.REMAINDER)
    internal = commands.add_parser("_offline-install")
    internal.add_argument("--wheel", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "fetch":
            print(fetch_wheel(args.output))
        elif args.command == "verify":
            verify_wheel(_read_regular(args.wheel), args.sha256, args.version)
            print(PIP_SHA256)
        elif args.command == "seed":
            install_pip(Path(sys.executable), args.wheel)
        elif args.command == "prepare":
            fetch_wheel(args.wheel)
            prepare(args.venv, args.wheel, args.github_env, args.github_path)
        elif args.command == "run":
            arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
            if not arguments:
                raise BootstrapError("A command is required")
            if (sys.prefix == sys.base_prefix
                    or importlib.metadata.version("pip") != PIP_VERSION):
                raise BootstrapError("Run requires a controller prepared with reviewed pip")
            with trusted_environment():
                return subprocess.run(arguments, check=False).returncode
        else:
            _offline_install(args.wheel)
    except (BootstrapError, OSError, subprocess.CalledProcessError,
            importlib.metadata.PackageNotFoundError) as error:
        print(f"Bootstrap refused: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
