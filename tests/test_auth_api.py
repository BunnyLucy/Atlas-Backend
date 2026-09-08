from sqlalchemy import select

from atlas_api.db import SessionLocal
from atlas_api.models import OutboxEvent


async def register_and_verify(client):
    response = await client.post("/api/v1/auth/register", json={
        "username": "atlas-user",
        "email": "user@example.com",
        "password": "correct-horse-battery-staple",
        "display_name": "Atlas User",
    })
    assert response.status_code == 201, response.text
    async with SessionLocal() as session:
        event = await session.scalar(select(OutboxEvent).where(OutboxEvent.kind == "email.verify"))
        assert event
        token = event.payload["token"]
    verified = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert verified.status_code == 200


async def test_registration_login_refresh_logout(client) -> None:
    await register_and_verify(client)
    login = await client.post("/api/v1/auth/login", json={
        "identifier": "user@example.com",
        "password": "correct-horse-battery-staple",
    })
    assert login.status_code == 200, login.text
    assert login.json()["accessToken"]
    assert client.cookies.get("atlas_refresh")

    refreshed = await client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text
    access_token = refreshed.json()["accessToken"]

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "user@example.com"

    logout = await client.post("/api/v1/auth/logout")
    assert logout.status_code == 204


async def test_login_uses_uniform_error(client) -> None:
    response = await client.post("/api/v1/auth/login", json={
        "identifier": "missing@example.com",
        "password": "not-the-password",
    })
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "LOGIN_FAILED"

