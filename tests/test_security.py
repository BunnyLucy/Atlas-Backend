import uuid

from atlas_api.config import Settings
from atlas_api.security import access_token, decode_access_token, hash_password, token_digest, verify_password


def settings() -> Settings:
    return Settings(jwt_secret="x" * 32)


def test_password_hash_round_trip() -> None:
    hashed = hash_password("a-long-test-password")
    assert hashed != "a-long-test-password"
    assert verify_password("a-long-test-password", hashed)
    assert not verify_password("wrong-password", hashed)


def test_access_token_round_trip() -> None:
    user_id = uuid.uuid4()
    token = access_token(settings(), user_id, "member")
    payload = decode_access_token(settings(), token)
    assert payload["sub"] == str(user_id)
    assert payload["role"] == "member"


def test_opaque_tokens_are_only_stored_as_digests() -> None:
    assert token_digest("secret") != "secret"
    assert len(token_digest("secret")) == 64

