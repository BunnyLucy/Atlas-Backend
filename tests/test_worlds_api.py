from tests.test_auth_api import register_and_verify


async def authenticated_client(client):
    await register_and_verify(client)
    login = await client.post("/api/v1/auth/login", json={
        "identifier": "atlas-user",
        "password": "correct-horse-battery-staple",
    })
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


async def test_canvas_and_wiki_share_objects_and_revisions(client) -> None:
    headers = await authenticated_client(client)
    created = await client.post("/api/v1/worlds", headers=headers, json={
        "id": "world-1", "slug": "world-1", "name": "World One",
        "tagline": "", "summary": "", "visibility": "private",
    })
    assert created.status_code == 201, created.text

    saved = await client.put("/api/v1/worlds/world-1/canvas", headers=headers, json={
        "expected_revision": 0,
        "schema_version": 1,
        "document": {"objects": [{"id": "character-1", "kind": "character", "title": "岑"}], "relations": []},
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == 1

    conflict = await client.put("/api/v1/worlds/world-1/canvas", headers=headers, json={
        "expected_revision": 0, "schema_version": 1, "document": {"objects": []},
    })
    assert conflict.status_code == 409
    assert conflict.json()["error"]["details"]["currentRevision"] == 1

    wiki = await client.put("/api/v1/worlds/world-1/objects/character-1", headers=headers, json={
        "expected_revision": 1,
        "kind": "character",
        "title": "岑（修订）",
        "payload": {"summary": "由 Wiki 更新"},
    })
    assert wiki.status_code == 200, wiki.text
    assert wiki.json()["revision"] == 2
    assert wiki.json()["canvasRevision"] == 2

    canvas = await client.get("/api/v1/worlds/world-1/canvas", headers=headers)
    assert canvas.json()["document"]["objects"][0]["title"] == "岑（修订）"

    history = await client.get("/api/v1/worlds/world-1/objects/character-1/revisions", headers=headers)
    assert history.status_code == 200
    assert history.json()["items"][0]["revision"] == 2

