from tests.test_auth_api import register_and_verify
from tests.test_memberships_api import login


async def setup_world_with_two_members(client):
    await register_and_verify(client, "owner", "owner@example.com")
    owner_headers, owner_id = await login(client, "owner")
    await register_and_verify(client, "creator", "creator@example.com")
    creator_headers, creator_id = await login(client, "creator")
    await client.post("/api/v1/worlds", headers=owner_headers, json={
        "id": "story-world", "slug": "story-world", "name": "Story World", "visibility": "private",
    })
    invitation = await client.post("/api/v1/worlds/story-world/invitations", headers=owner_headers, json={"identifier": "creator", "role": "participant"})
    await client.patch(f"/api/v1/memberships/invitations/{invitation.json()['id']}", headers=creator_headers, json={"decision": "accepted"})
    await client.put("/api/v1/worlds/story-world/canvas", headers=owner_headers, json={
        "expected_revision": 0, "schema_version": 1,
        "document": {"objects": [{"id": "owner-character", "kind": "character", "title": "岑"}], "relations": []},
    })
    character = await client.put("/api/v1/worlds/story-world/characters/owner-character", headers=owner_headers, json={
        "expected_revision": 0, "interaction_policy": "review", "custom_fields": {},
    })
    assert character.status_code == 200, character.text
    return owner_headers, owner_id, creator_headers, creator_id, character.json()["id"]


async def test_character_confirmation_then_owner_review_updates_shared_content(client) -> None:
    owner_headers, _, creator_headers, creator_id, profile_id = await setup_world_with_two_members(client)
    task = await client.post("/api/v1/worlds/story-world/tasks", headers=owner_headers, json={
        "title": "共同经历", "summary": "写一段共同经历", "status": "open", "capacity": 2,
    })
    assert task.status_code == 201, task.text
    task_id = task.json()["id"]
    joined = await client.post(f"/api/v1/worlds/story-world/tasks/{task_id}/join", headers=creator_headers)
    assert joined.status_code == 200

    submitted = await client.post("/api/v1/worlds/story-world/submissions", headers=creator_headers, json={
        "task_id": task_id, "title": "第七码头的交换", "body": "共同经历正文",
        "wiki_change_kind": "confirmedRelationship", "affected_object_ids": ["owner-character"],
        "payload": {"kind": "event"},
    })
    assert submitted.status_code == 201, submitted.text
    assert submitted.json()["state"] == "character_confirmation"
    submission_id = submitted.json()["id"]

    blocked = await client.post(f"/api/v1/worlds/story-world/submissions/{submission_id}/review", headers=owner_headers, json={"decision": "accepted"})
    assert blocked.status_code == 409

    confirmed = await client.patch(f"/api/v1/interaction-confirmations/{submission_id}/{profile_id}", headers=owner_headers, json={"decision": "accepted", "comment": "同意"})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["state"] == "pending"

    reviewed = await client.post(f"/api/v1/worlds/story-world/submissions/{submission_id}/review", headers=owner_headers, json={
        "decision": "accepted", "comment": "收录", "contribution_module": "writing",
        "scale_points": 2, "completion_points": 3, "specialty_points": 1,
    })
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["state"] == "accepted"

    canvas = await client.get("/api/v1/worlds/story-world/canvas", headers=creator_headers)
    assert any(item.get("sourceSubmissionID") == submission_id for item in canvas.json()["document"]["objects"])

    contribution = await client.get("/api/v1/worlds/story-world/contributions", headers=creator_headers)
    creator = next(item for item in contribution.json()["items"] if item["userID"] == creator_id)
    assert creator["score"] == 6

    notifications = await client.get("/api/v1/notifications", headers=creator_headers)
    assert any(item["type"] == "submission.review.result" for item in notifications.json()["items"])


async def test_character_owner_can_decline_submission(client) -> None:
    owner_headers, _, creator_headers, _, profile_id = await setup_world_with_two_members(client)
    submitted = await client.post("/api/v1/worlds/story-world/submissions", headers=creator_headers, json={
        "title": "不合适的互动", "affected_object_ids": ["owner-character"], "payload": {},
    })
    submission_id = submitted.json()["id"]
    declined = await client.patch(f"/api/v1/interaction-confirmations/{submission_id}/{profile_id}", headers=owner_headers, json={"decision": "declined", "comment": "不符合角色设定"})
    assert declined.status_code == 200
    assert declined.json()["state"] == "revision"
