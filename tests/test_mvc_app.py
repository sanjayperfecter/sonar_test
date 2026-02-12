from fastapi.testclient import TestClient

from src.mvc_app.main import create_app


def test_health_ok():
    client = TestClient(create_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_user_crud_happy_path():
    client = TestClient(create_app())

    # Create
    create_resp = client.post(
        "/users",
        json={"email": "user@example.com", "name": "Alice"},
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["email"] == "user@example.com"
    assert created["name"] == "Alice"
    assert isinstance(created["id"], str) and created["id"]

    # List
    list_resp = client.get("/users")
    assert list_resp.status_code == 200
    users = list_resp.json()
    assert any(u["id"] == created["id"] for u in users)

    # Get
    get_resp = client.get(f"/users/{created['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == created["id"]


def test_get_user_not_found():
    client = TestClient(create_app())
    resp = client.get("/users/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "User not found"

