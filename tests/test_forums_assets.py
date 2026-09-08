import pytest

from atlas_api.errors import AtlasError
from atlas_api.routers.assets import validate_upload
from tests.test_workflow_api import setup_world_with_two_members


async def test_forum_topic_reply_edit_and_soft_delete(client) -> None:
    owner_headers, _, creator_headers, _, _ = await setup_world_with_two_members(client)
    space = await client.post("/api/v1/worlds/story-world/forums", headers=owner_headers, json={"name": "主会场", "description": "企划讨论"})
    assert space.status_code == 201, space.text
    topic = await client.post("/api/v1/worlds/story-world/topics", headers=creator_headers, json={"space_id": space.json()["id"], "title": "世界线讨论", "body": "第一版想法"})
    assert topic.status_code == 201, topic.text
    topic_id = topic.json()["id"]

    reply = await client.post(f"/api/v1/worlds/story-world/topics/{topic_id}/posts", headers=owner_headers, json={"body": "企主回复"})
    assert reply.status_code == 201, reply.text
    post_id = reply.json()["id"]
    edited = await client.patch(f"/api/v1/worlds/story-world/posts/{post_id}", headers=owner_headers, json={"expected_revision": 1, "body": "企主修订回复"})
    assert edited.status_code == 200
    assert edited.json()["revision"] == 2

    pinned = await client.patch(f"/api/v1/worlds/story-world/topics/{topic_id}", headers=owner_headers, json={"expected_revision": 1, "is_pinned": True})
    assert pinned.status_code == 200
    assert pinned.json()["isPinned"] is True

    deleted = await client.delete(f"/api/v1/worlds/story-world/posts/{post_id}", headers=owner_headers)
    assert deleted.status_code == 204
    posts = await client.get(f"/api/v1/worlds/story-world/topics/{topic_id}/posts", headers=creator_headers)
    assert posts.json()["items"][0]["deleted"] is True
    assert posts.json()["items"][0]["body"] is None


def test_asset_validation() -> None:
    validate_upload("image/png", 1024)
    with pytest.raises(AtlasError) as forbidden:
        validate_upload("application/x-executable", 1024)
    assert forbidden.value.code == "ASSET_TYPE_FORBIDDEN"
    with pytest.raises(AtlasError) as too_large:
        validate_upload("image/png", 26 * 1024 * 1024)
    assert too_large.value.code == "ASSET_TOO_LARGE"
