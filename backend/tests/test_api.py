from fastapi.testclient import TestClient

from app.main import app

SAMPLES = [
    {
        "sender": "billing@northwind.test",
        "subject": "Invoice 1042 is ready",
        "body": "Your invoice for March is attached. Payment is due in 14 days.",
    },
    {
        "sender": "prize@lucky.test",
        "subject": "You have won the lottery",
        "body": "Claim your lottery winnings with a wire transfer today.",
    },
    {
        "sender": "deals@shop.test",
        "subject": "30% off this weekend",
        "body": "Limited time sale. Use the link below to unsubscribe.",
    },
]


def test_import_and_categorize():
    with TestClient(app) as client:
        login = client.post("/auth/dev", json={"email": "ada@example.com", "name": "Ada"})
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        imported = client.post("/emails/import", headers=headers, json={"messages": SAMPLES})
        assert imported.status_code == 200
        assert imported.json()["created"] == 3

        categories = client.get("/get-categories", headers=headers)
        counts = {item["slug"]: item["count"] for item in categories.json()["categories"]}
        assert counts["payment"] >= 1
        assert counts["spam"] >= 1
        assert counts["promotions"] >= 1

        payment = client.get("/emails", headers=headers, params={"category": "payment", "q": "invoice"})
        assert payment.status_code == 200
        assert len(payment.json()["emails"]) == 1
