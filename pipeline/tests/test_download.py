"""Download validation, without the network (httpx MockTransport)."""

import httpx
import pytest

from gully_pipeline import download


def _patch(monkeypatch, body: bytes, status=200, ctype="application/zip"):
    transport = httpx.MockTransport(lambda req: httpx.Response(status, content=body,
                                                               headers={"content-type": ctype}))
    real_stream = httpx.stream

    def stream(method, url, **kw):
        kw.pop("timeout", None)
        client = httpx.Client(transport=transport)
        return client.stream(method, url, **{k: v for k, v in kw.items() if k != "follow_redirects"})

    monkeypatch.setattr(download.httpx, "stream", stream)
    return real_stream


def test_zip_is_accepted(tmp_path, monkeypatch):
    _patch(monkeypatch, download.ZIP_MAGIC + b"\x00" * 100)
    out = download.download_dataset("ipl", tmp_path)
    assert out.read_bytes().startswith(download.ZIP_MAGIC)
    assert not list(tmp_path.glob("*.part"))


def test_html_instead_of_zip_fails_clearly(tmp_path, monkeypatch):
    _patch(monkeypatch, b"<!DOCTYPE html><title>Just a moment...</title>", ctype="text/html")
    with pytest.raises(download.DownloadError) as e:
        download.download_dataset("all", tmp_path)
    msg = str(e.value)
    assert "HTTP 200" in msg and "text/html" in msg and "Just a moment" in msg
    assert not (tmp_path / "all_json.zip").exists() and not list(tmp_path.glob("*.part"))


def test_register_header_checked(tmp_path, monkeypatch):
    _patch(monkeypatch, b"identifier,name,unique_name\n", ctype="text/csv")
    assert download.download_register(tmp_path).exists()
    _patch(monkeypatch, b"<html>blocked</html>", ctype="text/html")
    with pytest.raises(download.DownloadError):
        download.download_register(tmp_path)
