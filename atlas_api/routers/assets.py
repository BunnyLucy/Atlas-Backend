import asyncio
import re
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from qcloud_cos import CosConfig, CosS3Client
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..db import get_session
from ..dependencies import WorldAccess, world_access
from ..errors import AtlasError
from ..models import Asset, AssetReference, AssetVersion, AuditEvent, OutboxEvent, PendingUpload
from ..schemas import AssetCompleteInput, AssetReferenceInput, AssetVersionCompleteInput, UploadSignInput

router = APIRouter(tags=["assets"])
ALLOWED_EXACT = {"application/pdf", "application/zip", "text/plain", "text/markdown"}
ALLOWED_PREFIXES = ("image/", "audio/", "video/")


def cos_client(settings: Settings) -> CosS3Client:
    if not all((settings.cos_secret_id, settings.cos_secret_key, settings.cos_region, settings.cos_bucket)):
        raise AtlasError(503, "COS_DISABLED", "腾讯云 COS 尚未配置")
    return CosS3Client(CosConfig(
        Region=settings.cos_region,
        SecretId=settings.cos_secret_id,
        SecretKey=settings.cos_secret_key.get_secret_value(),
        Scheme="https",
    ))


def validate_upload(content_type: str, byte_size: int) -> None:
    if content_type not in ALLOWED_EXACT and not content_type.startswith(ALLOWED_PREFIXES):
        raise AtlasError(422, "ASSET_TYPE_FORBIDDEN", "不支持该文件类型")
    limit = 25 * 1024 * 1024 if content_type.startswith("image/") else 100 * 1024 * 1024
    if byte_size > limit:
        raise AtlasError(413, "ASSET_TOO_LARGE", f"文件不能超过 {limit // 1024 // 1024} MB")


async def create_pending_upload(body: UploadSignInput, access: WorldAccess, session: AsyncSession, settings: Settings) -> dict:
    access.require_write()
    validate_upload(body.content_type, body.byte_size)
    extension = re.sub(r"[^A-Za-z0-9.]", "", body.filename.rsplit("/", 1)[-1])[-80:]
    upload_id = uuid.uuid4()
    key = f"worlds/{access.world.id}/assets/{datetime.now(UTC):%Y/%m}/{upload_id}/{extension or 'file'}"
    pending = PendingUpload(id=upload_id, world_id=access.world.id, user_id=access.user.id, object_key=key, filename=body.filename, content_type=body.content_type, byte_size=body.byte_size, expires_at=datetime.now(UTC) + timedelta(minutes=15))
    session.add(pending); await session.commit()
    client = cos_client(settings)
    url = await asyncio.to_thread(client.get_presigned_url, Method="PUT", Bucket=settings.cos_bucket, Key=key, Expired=900, Headers={"Content-Type": body.content_type})
    return {"uploadID": str(upload_id), "objectKey": key, "uploadURL": url, "method": "PUT", "headers": {"Content-Type": body.content_type}, "expiresAt": pending.expires_at.isoformat()}


@router.post("/worlds/{world_id}/uploads/sign")
async def sign_upload(body: UploadSignInput, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)) -> dict:
    return await create_pending_upload(body, access, session, settings)


async def verify_pending(upload_id: str, object_key: str, content_type: str, byte_size: int, access: WorldAccess, session: AsyncSession, settings: Settings) -> PendingUpload:
    try: parsed_id = uuid.UUID(upload_id)
    except ValueError: raise AtlasError(422, "UPLOAD_ID_INVALID", "上传 ID 无效") from None
    pending = await session.scalar(select(PendingUpload).where(PendingUpload.id == parsed_id).with_for_update())
    if not pending or pending.world_id != access.world.id or pending.user_id != access.user.id or pending.completed_at:
        raise AtlasError(404, "UPLOAD_NOT_FOUND", "上传记录不存在")
    if pending.expires_at <= datetime.now(UTC): raise AtlasError(410, "UPLOAD_EXPIRED", "上传凭证已过期")
    if (pending.object_key, pending.content_type, pending.byte_size) != (object_key, content_type, byte_size):
        raise AtlasError(422, "UPLOAD_MISMATCH", "文件信息与上传凭证不一致")
    if settings.cos_verify_upload:
        client = cos_client(settings)
        try:
            metadata = await asyncio.to_thread(client.head_object, Bucket=settings.cos_bucket, Key=object_key)
            actual_size = int(metadata.get("Content-Length", -1))
        except Exception as exc:
            raise AtlasError(422, "UPLOAD_NOT_FOUND_IN_COS", "COS 中未找到已上传文件") from exc
        if actual_size != byte_size: raise AtlasError(422, "UPLOAD_SIZE_MISMATCH", "COS 文件大小不一致")
    pending.completed_at = datetime.now(UTC)
    return pending


def public_url(settings: Settings, key: str) -> str | None:
    return f"{str(settings.cos_public_base_url).rstrip('/')}/{key}" if settings.cos_public_base_url else None


@router.post("/worlds/{world_id}/assets", status_code=201)
async def complete_asset(body: AssetCompleteInput, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)) -> dict:
    access.require_write(); validate_upload(body.content_type, body.byte_size)
    await verify_pending(body.upload_id, body.object_key, body.content_type, body.byte_size, access, session, settings)
    asset = Asset(world_id=access.world.id, owner_id=access.user.id, name=body.name, category=body.category, metadata_=body.metadata)
    session.add(asset); await session.flush()
    version = AssetVersion(asset_id=asset.id, version=1, object_key=body.object_key, content_type=body.content_type, byte_size=body.byte_size, checksum=body.checksum, public_url=public_url(settings, body.object_key), created_by=access.user.id)
    session.add(version)
    if body.content_type.startswith("image/"):
        session.add(OutboxEvent(kind="asset.thumbnail", payload={"assetID": str(asset.id), "version": 1, "objectKey": body.object_key}))
    session.add(AuditEvent(actor_id=access.user.id, world_id=access.world.id, action="asset.created", target_type="asset", target_id=str(asset.id)))
    await session.commit()
    return {"id": str(asset.id), "name": asset.name, "category": asset.category, "version": 1, "url": version.public_url}


@router.get("/worlds/{world_id}/assets")
async def list_assets(access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    rows = (await session.execute(select(Asset, AssetVersion).join(AssetVersion, (AssetVersion.asset_id == Asset.id) & (AssetVersion.version == Asset.current_version)).where(Asset.world_id == access.world.id, Asset.deleted_at.is_(None)).order_by(Asset.updated_at.desc()))).all()
    return {"items": [{"id": str(asset.id), "name": asset.name, "category": asset.category, "version": version.version, "contentType": version.content_type, "byteSize": version.byte_size, "url": version.public_url, "metadata": asset.metadata_} for asset, version in rows]}


@router.post("/worlds/{world_id}/assets/{asset_id}/versions", status_code=201)
async def complete_asset_version(asset_id: uuid.UUID, body: AssetVersionCompleteInput, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)) -> dict:
    access.require_write(); validate_upload(body.content_type, body.byte_size)
    asset = await session.scalar(select(Asset).where(Asset.id == asset_id, Asset.world_id == access.world.id, Asset.deleted_at.is_(None)).with_for_update())
    if not asset: raise AtlasError(404, "ASSET_NOT_FOUND", "资产不存在")
    manager = access.user.role.value == "admin" or (access.role and access.role.value in {"owner", "manager"})
    if asset.owner_id != access.user.id and not manager: raise AtlasError(403, "ASSET_EDIT_FORBIDDEN", "无权更新该资产")
    await verify_pending(body.upload_id, body.object_key, body.content_type, body.byte_size, access, session, settings)
    version_number = asset.current_version + 1
    version = AssetVersion(asset_id=asset.id, version=version_number, object_key=body.object_key, content_type=body.content_type, byte_size=body.byte_size, checksum=body.checksum, public_url=public_url(settings, body.object_key), created_by=access.user.id)
    session.add(version); asset.current_version = version_number
    if body.content_type.startswith("image/"): session.add(OutboxEvent(kind="asset.thumbnail", payload={"assetID": str(asset.id), "version": version_number, "objectKey": body.object_key}))
    await session.commit()
    return {"id": str(asset.id), "version": version_number, "url": version.public_url}


@router.post("/worlds/{world_id}/assets/{asset_id}/references", status_code=201)
async def reference_asset(asset_id: uuid.UUID, body: AssetReferenceInput, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    access.require_write()
    asset = await session.get(Asset, asset_id)
    if not asset or asset.world_id != access.world.id or asset.deleted_at: raise AtlasError(404, "ASSET_NOT_FOUND", "资产不存在")
    existing = await session.get(AssetReference, (asset_id, access.world.id, body.target_type, body.target_id))
    if not existing: session.add(AssetReference(asset_id=asset_id, world_id=access.world.id, target_type=body.target_type, target_id=body.target_id, created_by=access.user.id))
    await session.commit()
    return {"assetID": str(asset_id), "targetType": body.target_type, "targetID": body.target_id}


@router.delete("/worlds/{world_id}/assets/{asset_id}", status_code=204)
async def delete_asset(asset_id: uuid.UUID, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> None:
    access.require_write()
    asset = await session.get(Asset, asset_id)
    if not asset or asset.world_id != access.world.id or asset.deleted_at: raise AtlasError(404, "ASSET_NOT_FOUND", "资产不存在")
    manager = access.user.role.value == "admin" or (access.role and access.role.value in {"owner", "manager"})
    if asset.owner_id != access.user.id and not manager: raise AtlasError(403, "ASSET_DELETE_FORBIDDEN", "无权删除该资产")
    asset.deleted_at = datetime.now(UTC); await session.commit()
