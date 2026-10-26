"""Offline security controls for the authenticated bootstrap."""
import datetime
import hashlib
import importlib
import os
import socket
import ssl
import subprocess
import sys
import threading
import venv
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

bootstrap = importlib.import_module("tools.bootstrap_python")


@pytest.fixture(scope="module")
def wheel():
    path = bootstrap.default_wheel()
    assert path.is_file(), "Prepare the approved bootstrap wheel before running tests"
    bootstrap.verify_wheel(path.read_bytes())
    return path


def test_approved_wheel(wheel):
    assert bootstrap.verify_wheel(wheel.read_bytes()) == wheel.read_bytes()


def test_modified_wheel_refused(wheel):
    with pytest.raises(bootstrap.BootstrapError, match="SHA-256"):
        bootstrap.verify_wheel(wheel.read_bytes() + b"modified")


def test_unapproved_hash_cannot_replace_reference(wheel):
    with pytest.raises(bootstrap.BootstrapError, match="reviewed"):
        bootstrap.verify_wheel(wheel.read_bytes(), expected_hash="0" * 64)


def test_wrong_version_refused(wheel):
    with pytest.raises(bootstrap.BootstrapError, match="reviewed"):
        bootstrap.verify_wheel(wheel.read_bytes(), expected_version="26.2.1")


def test_wheel_size_limit():
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.verify_wheel(b"x" * (bootstrap.MAX_WHEEL_BYTES + 1))


def test_snapshot_prevents_original_file_swap(wheel, tmp_path):
    original = tmp_path / "input.whl"
    original.write_bytes(wheel.read_bytes())
    with bootstrap.staged_wheel(original) as snapshot:
        original.write_bytes(b"changed after validation")
        assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == bootstrap.PIP_SHA256
        assert snapshot.parent.stat().st_mode & 0o077 == 0


def test_symlink_input_refused(wheel, tmp_path):
    link = tmp_path / "pip.whl"
    link.symlink_to(wheel)
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap._read_regular(link)


def test_existing_corrupt_cache_does_not_download(monkeypatch, tmp_path):
    output = tmp_path / "pip.whl"
    output.write_bytes(b"corrupt")
    monkeypatch.setattr(bootstrap.urllib.request, "build_opener",
                        lambda *args: pytest.fail("must not hide cache corruption"))
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.fetch_wheel(output)


@pytest.mark.parametrize("target", [
    "http://files.pythonhosted.org/pip.whl",
    "https://attacker.invalid/pip.whl",
    bootstrap.PIP_URL,
])
def test_all_bootstrap_redirects_refused(target):
    with pytest.raises(bootstrap.BootstrapError, match="redirect"):
        bootstrap._NoRedirect().redirect_request(None, None, 302, "redirect", {}, target)


def test_no_network_is_not_a_success(monkeypatch, tmp_path):
    class OfflineOpener:
        def open(self, *args, **kwargs):
            raise bootstrap.urllib.error.URLError("network unavailable")

    monkeypatch.setattr(bootstrap.urllib.request, "build_opener", lambda *args: OfflineOpener())
    output = tmp_path / "pip.whl"
    with pytest.raises(bootstrap.BootstrapError, match="unavailable"):
        bootstrap.fetch_wheel(output)
    assert not output.exists()


def test_rejected_ca_bundle(monkeypatch, tmp_path):
    fake = tmp_path / "unapproved.pem"
    fake.write_bytes(b"not the approved anchors")
    monkeypatch.setattr(bootstrap, "CA_FILE", fake)
    with pytest.raises(bootstrap.BootstrapError, match="Unapproved"):
        bootstrap.tls_context()


def test_explicit_context_excludes_denied_root(monkeypatch, tmp_path):
    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "untrusted-system.pem"))
    context = bootstrap.tls_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert bootstrap.DENIED_ROOT not in {
        hashlib.sha256(cert).hexdigest() for cert in context.get_ca_certs(binary_form=True)
    }


def test_unapproved_server_certificate_is_rejected(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - datetime.timedelta(minutes=1))
                   .not_valid_after(now + datetime.timedelta(hours=1))
                   .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]),
                                  critical=False).sign(key, hashes.SHA256()))
    certfile, keyfile = tmp_path / "cert.pem", tmp_path / "key.pem"
    certfile.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                        serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption()))
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(certfile, keyfile)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(5)

    def server():
        try:
            connection, _ = listener.accept()
            with connection, pytest.raises(ssl.SSLError):
                server_context.wrap_socket(connection, server_side=True)
        finally:
            listener.close()

    thread = threading.Thread(target=server)
    thread.start()
    try:
        with socket.create_connection(listener.getsockname(), timeout=5) as connection, \
                pytest.raises(ssl.SSLCertVerificationError):
            bootstrap.tls_context().wrap_socket(connection, server_hostname="localhost")
    finally:
        thread.join(timeout=10)
    assert not thread.is_alive()


@pytest.mark.parametrize("event", ["socket.connect", "socket.getaddrinfo", "subprocess.Popen"])
def test_offline_guard_refuses_network_and_children(event):
    with pytest.raises(PermissionError):
        bootstrap._offline_guard(event, ())


def test_environment_restores_even_if_ca_validation_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("PIP_INDEX_URL", "https://example.invalid/simple")
    monkeypatch.setattr(bootstrap, "CA_FILE", tmp_path / "missing")
    before = os.environ.copy()
    with pytest.raises(bootstrap.BootstrapError), bootstrap.trusted_environment():
        pytest.fail("invalid anchors cannot enter trusted scope")
    assert os.environ == before


def test_trust_scope_excludes_system_directory(monkeypatch):
    monkeypatch.setenv("PIP_TRUSTED_HOST", "attacker.invalid")
    with bootstrap.trusted_environment():
        assert "PIP_TRUSTED_HOST" not in os.environ
        assert Path(os.environ["SSL_CERT_FILE"]).is_file()
        assert list(Path(os.environ["SSL_CERT_DIR"]).iterdir()) == []
    assert os.environ["PIP_TRUSTED_HOST"] == "attacker.invalid"


def test_auditor_settings_survive_trust_scope(monkeypatch, tmp_path):
    settings = {
        "PIP_AUDIT_FORMAT": "json",
        "PIP_AUDIT_VULNERABILITY_SERVICE": "osv",
        "PIP_AUDIT_OSV_URL": "https://osv.example.invalid",
        "PIP_AUDIT_OUTPUT": str(tmp_path / "audit.json"),
    }
    for key, value in settings.items():
        monkeypatch.setenv(key, value)
    with bootstrap.trusted_environment():
        assert {key: os.environ.get(key) for key in settings} == settings


def test_nonvenv_directory_is_preserved(wheel, tmp_path):
    destination = tmp_path / "existing"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("keep")
    with pytest.raises(bootstrap.BootstrapError, match="overwrite"):
        bootstrap.prepare(destination, wheel)
    assert marker.read_text() == "keep"


def test_real_seed_free_bootstrap(wheel, tmp_path):
    destination = tmp_path / "controller"
    bootstrap.prepare(destination, wheel)
    result = subprocess.check_output([
        str(destination / "bin/python"), "-I", "-B", "-c",
        ("import importlib.metadata as m,sys; "
         "assert sys.prefix != sys.base_prefix; print(m.version('pip'))"),
    ], text=True).strip()
    assert result == bootstrap.PIP_VERSION
    assert "include-system-site-packages = false" in (destination / "pyvenv.cfg").read_text()


def test_no_seed_created_by_venv_builder(tmp_path):
    destination = tmp_path / "without-seed"
    venv.EnvBuilder(with_pip=False).create(destination)
    result = subprocess.check_output([
        str(destination / "bin/python"), "-I", "-B", "-c",
        "import importlib.util; print(importlib.util.find_spec('pip'))",
    ], text=True)
    assert result.strip() == "None"


def test_base_python_refused_before_install(wheel):
    result = subprocess.run([
        sys._base_executable, "-I", "-B", str(Path(bootstrap.__file__)),
        "_offline-install", "--wheel", str(wheel),
    ], capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert "base/system Python" in result.stderr
