import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.errors import ProviderError
from app.services.imap_hosts import normalize_mailbox_password, resolve_imap_host


def test_known_mailbox_hosts():
    assert resolve_imap_host("ada@gmail.com") == "imap.gmail.com"
    assert resolve_imap_host("ada@outlook.com") == "outlook.office365.com"
    assert resolve_imap_host("ada@yahoo.co.in") == "imap.mail.yahoo.com"
    assert resolve_imap_host("ada@company.example") == "imap.company.example"


def test_proton_is_rejected():
    with pytest.raises(ProviderError):
        resolve_imap_host("ada@proton.me")


def test_gmail_app_password_spaces_are_removed():
    assert normalize_mailbox_password("abcd efgh ijkl mnop") == "abcdefghijklmnop"
    assert normalize_mailbox_password("keep spaces here") == "keep spaces here"


def test_mailbox_login_verifies_and_stores_account(monkeypatch):
    seen = {}

    def fake_verify(host, username, password, port=993, use_ssl=True):
        seen.update(host=host, username=username, password=password, port=port, use_ssl=use_ssl)

    monkeypatch.setattr("app.api.auth.verify_login", fake_verify)
    with TestClient(app) as client:
        response = client.post(
            "/auth/mailbox",
            json={"email": "Ada@gmail.com", "password": "abcd efgh ijkl mnop"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["access_token"]
        assert body["user"]["email"] == "ada@gmail.com"
        assert body["user"]["imap_accounts"] == [
            {"host": "imap.gmail.com", "username": "ada@gmail.com", "port": 993}
        ]
    assert seen == {
        "host": "imap.gmail.com",
        "username": "ada@gmail.com",
        "password": "abcdefghijklmnop",
        "port": 993,
        "use_ssl": True,
    }


def test_mailbox_login_reports_a_rejected_password(monkeypatch):
    def fake_verify(*_args, **_kwargs):
        raise ProviderError("The mail server rejected this password.")

    monkeypatch.setattr("app.api.auth.verify_login", fake_verify)
    with TestClient(app) as client:
        response = client.post("/auth/mailbox", json={"email": "ada@gmail.com", "password": "wrong-password"})
        assert response.status_code == 401
        assert "rejected" in response.json()["detail"]


def test_fetch_without_a_mailbox_explains_why():
    with TestClient(app) as client:
        login = client.post("/auth/dev", json={"email": "empty@example.com"})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        fetched = client.post("/fetch-emails", headers=headers, json={"limit": 5})
        assert fetched.status_code == 200
        assert fetched.json()["fetched"] == 0
        assert fetched.json()["errors"]
