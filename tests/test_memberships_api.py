from tests.test_auth_api import register_and_verify


async def login(client, identifier: str) -> tuple[dict, str]:
    response = await client.post("/api/v1/auth/login", json={
        "identifier": identifier,
        "password": "correct-horse-battery-staple",
    })
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}, response.json()["user"]["id"]


async def test_invitation_role_change_and_ownership_transfer(client) -> None:
    await register_and_verify(client, "owner", "owner@example.com")
    owner_headers, owner_id = await login(client, "owner")
    await register_and_verify(client, "member", "member@example.com")
    member_headers, member_id = await login(client, "member")

    world = await client.post("/api/v1/worlds", headers=owner_headers, json={
        "id": "shared-world", "slug": "shared-world", "name": "Shared World",
        "visibility": "private",
    })
    assert world.status_code == 201, world.text

    invitation = await client.post("/api/v1/worlds/shared-world/invitations", headers=owner_headers, json={
        "identifier": "member@example.com", "role": "participant",
    })
    assert invitation.status_code == 201, invitation.text
    invitation_id = invitation.json()["id"]

    accepted = await client.patch(f"/api/v1/memberships/invitations/{invitation_id}", headers=member_headers, json={"decision": "accepted"})
    assert accepted.status_code == 200, accepted.text

    promoted = await client.patch(f"/api/v1/worlds/shared-world/members/{member_id}", headers=owner_headers, json={"role": "manager"})
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "manager"

    transferred = await client.post("/api/v1/worlds/shared-world/transfer-ownership", headers=owner_headers, json={"new_owner_id": member_id})
    assert transferred.status_code == 200, transferred.text
    assert transferred.json()["ownerID"] == member_id

    members = await client.get("/api/v1/worlds/shared-world/members", headers=member_headers)
    roles = {item["userID"]: item["role"] for item in members.json()["items"]}
    assert roles[member_id] == "owner"
    assert roles[owner_id] == "manager"


async def test_public_world_join_request(client) -> None:
    await register_and_verify(client, "owner", "owner@example.com")
    owner_headers, _ = await login(client, "owner")
    await register_and_verify(client, "applicant", "applicant@example.com")
    applicant_headers, applicant_id = await login(client, "applicant")

    await client.post("/api/v1/worlds", headers=owner_headers, json={
        "id": "public-world", "slug": "public-world", "name": "Public World",
        "visibility": "public",
    })
    requested = await client.post("/api/v1/worlds/public-world/join-requests", headers=applicant_headers, json={"message": "想加入", "role": "participant"})
    assert requested.status_code == 201, requested.text

    pending = await client.get("/api/v1/worlds/public-world/join-requests", headers=owner_headers)
    assert pending.status_code == 200
    assert pending.json()["items"][0]["userID"] == applicant_id

    reviewed = await client.patch(f"/api/v1/worlds/public-world/join-requests/{requested.json()['id']}", headers=owner_headers, json={"decision": "accepted"})
    assert reviewed.status_code == 200, reviewed.text

    members = await client.get("/api/v1/worlds/public-world/members", headers=applicant_headers)
    assert any(item["userID"] == applicant_id for item in members.json()["items"])
