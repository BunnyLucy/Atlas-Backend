import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from atlas_api.db import engine
from atlas_api.main import app


@pytest_asyncio.fixture(autouse=True)
async def clean_database():
    async with engine.begin() as connection:
        await connection.execute(text(
            "TRUNCATE asset_references, asset_versions, pending_uploads, assets, forum_posts, "
            "forum_topics, forum_spaces, outbox_events, audit_events, notifications, contribution_events, "
            "submission_reviews, submission_confirmations, submissions, task_participants, "
            "world_tasks, character_profiles, wiki_revisions, world_objects, canvas_revisions, "
            "world_maps, canvas_documents, world_memberships, worlds, "
            "world_join_requests, world_invitations, refresh_sessions, auth_tokens, "
            "oauth_accounts, user_profiles, users CASCADE"
        ))
    yield


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
