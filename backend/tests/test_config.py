import os

from src.core.config import discard_invalid_ssl_cert_file


def test_discard_invalid_ssl_cert_file(
    monkeypatch,
    tmp_path,
) -> None:
    missing_cert = tmp_path / "missing.pem"
    monkeypatch.setenv("SSL_CERT_FILE", str(missing_cert))

    discard_invalid_ssl_cert_file()

    assert "SSL_CERT_FILE" not in os.environ


def test_preserve_valid_ssl_cert_file(
    monkeypatch,
    tmp_path,
) -> None:
    cert_file = tmp_path / "custom.pem"
    cert_file.write_text("custom certificate", encoding="utf-8")
    monkeypatch.setenv("SSL_CERT_FILE", str(cert_file))

    discard_invalid_ssl_cert_file()

    assert os.environ["SSL_CERT_FILE"] == str(cert_file)
