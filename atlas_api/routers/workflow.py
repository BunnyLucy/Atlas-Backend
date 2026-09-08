import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..dependencies import WorldAccess, current_user, world_access
from ..errors import AtlasError
from ..models import (
    AuditEvent, CanvasDocument, CanvasRevision, CharacterProfile, ContributionEvent,
    Notification, Submission, SubmissionConfirmation, SubmissionReview, TaskParticipant,
    User, WikiRevision, WorldMembership, WorldObject, WorldRole, WorldTask,
)
from ..schemas import CharacterProfilePut, ConfirmationDecision, ReviewDecision, SubmissionCreate, SubmissionUpdate, TaskCreate, TaskUpdate

router = APIRouter(tags=["collaboration"])


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        raise AtlasError(422, "DATETIME_INVALID", "日期时间格式无效") from None


def task_payload(task: WorldTask, participants: int = 0, joined: bool = False) -> dict:
    return {
        "id": str(task.id), "worldID": task.world_id, "title": task.title,
        "summary": task.summary, "status": task.status, "capacity": task.capacity,
        "participants": participants, "joined": joined,
        "deadlineAt": task.deadline_at.isoformat() if task.deadline_at else None,
        "objectIDs": task.object_ids, "payload": task.payload, "revision": task.revision,
    }


def submission_payload(item: Submission) -> dict:
    return {
        "id": str(item.id), "worldID": item.world_id,
        "taskID": str(item.task_id) if item.task_id else None,
        "authorID": str(item.author_id), "title": item.title, "body": item.body,
        "state": item.state, "destination": item.destination,
        "wikiChangeKind": item.wiki_change_kind, "targetObjectID": item.target_object_id,
        "affectedObjectIDs": item.affected_object_ids, "payload": item.payload,
        "revision": item.revision,
        "submittedAt": item.submitted_at.isoformat() if item.submitted_at else None,
    }


@router.put("/worlds/{world_id}/characters/{object_id}")
async def put_character_profile(object_id: str, body: CharacterProfilePut, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    access.require_write()
    obj = await session.get(WorldObject, (access.world.id, object_id))
    if not obj or obj.kind != "character":
        raise AtlasError(404, "CHARACTER_NOT_FOUND", "角色不存在")
    profile = await session.scalar(select(CharacterProfile).where(CharacterProfile.world_id == access.world.id, CharacterProfile.object_id == object_id).with_for_update())
    current = profile.revision if profile else 0
    if current != body.expected_revision:
        raise AtlasError(409, "REVISION_CONFLICT", "角色档案已更新", {"currentRevision": current})
    if profile:
        if profile.owner_id != access.user.id and access.role not in {WorldRole.owner, WorldRole.manager}:
            raise AtlasError(403, "CHARACTER_EDIT_FORBIDDEN", "无权编辑该角色档案")
        profile.interaction_policy = body.interaction_policy
        profile.custom_fields = body.custom_fields
        profile.revision += 1
    else:
        profile = CharacterProfile(world_id=access.world.id, object_id=object_id, owner_id=access.user.id, interaction_policy=body.interaction_policy, custom_fields=body.custom_fields)
        session.add(profile)
    await session.commit()
    return {"id": str(profile.id), "objectID": object_id, "ownerID": str(profile.owner_id), "interactionPolicy": profile.interaction_policy, "customFields": profile.custom_fields, "revision": profile.revision}


@router.get("/worlds/{world_id}/tasks")
async def list_tasks(access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    counts = select(TaskParticipant.task_id, func.count().label("count")).where(TaskParticipant.left_at.is_(None)).group_by(TaskParticipant.task_id).subquery()
    joined = select(TaskParticipant.task_id.label("joined_task")).where(TaskParticipant.user_id == access.user.id, TaskParticipant.left_at.is_(None)).subquery()
    rows = (await session.execute(select(WorldTask, func.coalesce(counts.c.count, 0), joined.c.joined_task).outerjoin(counts, counts.c.task_id == WorldTask.id).outerjoin(joined, joined.c.joined_task == WorldTask.id).where(WorldTask.world_id == access.world.id).order_by(WorldTask.created_at.desc()))).all()
    return {"items": [task_payload(task, count, joined_id is not None) for task, count, joined_id in rows]}


@router.post("/worlds/{world_id}/tasks", status_code=201)
async def create_task(body: TaskCreate, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    access.require_manage()
    access.require_write()
    task = WorldTask(world_id=access.world.id, creator_id=access.user.id, title=body.title, summary=body.summary, status=body.status, capacity=body.capacity, deadline_at=parse_datetime(body.deadline_at), object_ids=body.object_ids, payload=body.payload)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task_payload(task)


@router.patch("/worlds/{world_id}/tasks/{task_id}")
async def update_task(task_id: uuid.UUID, body: TaskUpdate, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    access.require_manage()
    access.require_write()
    task = await session.scalar(select(WorldTask).where(WorldTask.id == task_id, WorldTask.world_id == access.world.id).with_for_update())
    if not task:
        raise AtlasError(404, "TASK_NOT_FOUND", "任务不存在")
    if task.revision != body.expected_revision:
        raise AtlasError(409, "REVISION_CONFLICT", "任务已更新", {"currentRevision": task.revision})
    transitions = {"draft": {"open", "cancelled"}, "open": {"active", "cancelled"}, "active": {"settling", "cancelled"}, "settling": {"completed", "active"}, "completed": set(), "cancelled": set()}
    if body.status and body.status != task.status and body.status not in transitions[task.status]:
        raise AtlasError(409, "TASK_TRANSITION_INVALID", "任务状态不能这样变更")
    values = body.model_dump(exclude_none=True, exclude={"expected_revision", "deadline_at"})
    for key, value in values.items():
        setattr(task, key, value)
    if body.deadline_at is not None:
        task.deadline_at = parse_datetime(body.deadline_at)
    task.revision += 1
    await session.commit()
    count = await session.scalar(select(func.count()).select_from(TaskParticipant).where(TaskParticipant.task_id == task.id, TaskParticipant.left_at.is_(None)))
    return task_payload(task, count or 0)


@router.post("/worlds/{world_id}/tasks/{task_id}/join")
async def join_task(task_id: uuid.UUID, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    access.require_write()
    task = await session.scalar(select(WorldTask).where(WorldTask.id == task_id, WorldTask.world_id == access.world.id).with_for_update())
    if not task or task.status not in {"open", "active"}:
        raise AtlasError(409, "TASK_NOT_JOINABLE", "任务当前不可承接")
    participant = await session.get(TaskParticipant, (task.id, access.user.id))
    active_count = await session.scalar(select(func.count()).select_from(TaskParticipant).where(TaskParticipant.task_id == task.id, TaskParticipant.left_at.is_(None))) or 0
    if participant and participant.left_at is None:
        raise AtlasError(409, "TASK_ALREADY_JOINED", "已经承接该任务")
    if task.capacity is not None and active_count >= task.capacity:
        raise AtlasError(409, "TASK_FULL", "任务人数已满")
    if participant:
        participant.left_at = None
        participant.joined_at = datetime.now(UTC)
    else:
        session.add(TaskParticipant(task_id=task.id, user_id=access.user.id))
    if task.status == "open":
        task.status = "active"
        task.revision += 1
    await session.commit()
    return {"joined": True}


@router.delete("/worlds/{world_id}/tasks/{task_id}/join", status_code=204)
async def leave_task(task_id: uuid.UUID, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> None:
    participant = await session.scalar(select(TaskParticipant).where(TaskParticipant.task_id == task_id, TaskParticipant.user_id == access.user.id).with_for_update())
    if not participant or participant.left_at:
        raise AtlasError(404, "TASK_PARTICIPATION_NOT_FOUND", "尚未承接该任务")
    pending = await session.scalar(select(Submission.id).where(Submission.task_id == task_id, Submission.author_id == access.user.id, Submission.state.in_(["character_confirmation", "pending"])))
    if pending:
        raise AtlasError(409, "TASK_HAS_ACTIVE_SUBMISSION", "存在处理中的投稿，无法退出任务")
    participant.left_at = datetime.now(UTC)
    await session.commit()


@router.get("/worlds/{world_id}/submissions")
async def list_submissions(access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session), state: str | None = Query(default=None)) -> dict:
    query = select(Submission).where(Submission.world_id == access.world.id)
    if access.role not in {WorldRole.owner, WorldRole.manager} and access.user.role.value != "admin":
        query = query.where(Submission.author_id == access.user.id)
    if state:
        query = query.where(Submission.state == state)
    items = (await session.scalars(query.order_by(Submission.created_at.desc()))).all()
    return {"items": [submission_payload(item) for item in items]}


@router.post("/worlds/{world_id}/submissions", status_code=201)
async def create_submission(body: SubmissionCreate, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    access.require_write()
    task_id = None
    if body.task_id:
        try:
            task_id = uuid.UUID(body.task_id)
        except ValueError:
            raise AtlasError(422, "TASK_ID_INVALID", "任务 ID 无效") from None
        task = await session.get(WorldTask, task_id)
        participant = await session.get(TaskParticipant, (task_id, access.user.id))
        if not task or task.world_id != access.world.id or not participant or participant.left_at:
            raise AtlasError(403, "TASK_SUBMISSION_FORBIDDEN", "未承接该任务")
    profiles = (await session.scalars(select(CharacterProfile).where(CharacterProfile.world_id == access.world.id, CharacterProfile.object_id.in_(body.affected_object_ids)))).all() if body.affected_object_ids else []
    forbidden = [profile for profile in profiles if profile.owner_id != access.user.id and profile.interaction_policy == "forbidden"]
    if forbidden:
        raise AtlasError(403, "CHARACTER_INTERACTION_FORBIDDEN", "投稿涉及禁止互动的角色")
    confirmations = [profile for profile in profiles if profile.owner_id != access.user.id and profile.interaction_policy == "review"]
    item = Submission(world_id=access.world.id, task_id=task_id, author_id=access.user.id, title=body.title, body=body.body, state="character_confirmation" if confirmations else "pending", destination=body.destination, wiki_change_kind=body.wiki_change_kind, target_object_id=body.target_object_id, affected_object_ids=body.affected_object_ids, payload=body.payload, submitted_at=datetime.now(UTC))
    session.add(item)
    await session.flush()
    for profile in confirmations:
        session.add(SubmissionConfirmation(submission_id=item.id, confirmer_user_id=profile.owner_id, character_profile_id=profile.id))
        session.add(Notification(recipient_user_id=profile.owner_id, world_id=access.world.id, type="submission.character-confirmation", title=f"角色互动等待确认：{body.title}", summary="投稿涉及你的角色", dedupe_key=f"submission-confirmation:{item.id}:{profile.id}", action_type="submission-confirmation", action_target=str(item.id)))
    await session.commit()
    return submission_payload(item)


@router.patch("/worlds/{world_id}/submissions/{submission_id}")
async def update_submission(submission_id: uuid.UUID, body: SubmissionUpdate, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    access.require_write()
    item = await session.scalar(select(Submission).where(Submission.id == submission_id, Submission.world_id == access.world.id).with_for_update())
    if not item or item.author_id != access.user.id:
        raise AtlasError(404, "SUBMISSION_NOT_FOUND", "投稿不存在")
    if item.state not in {"draft", "revision", "withdrawn"}:
        raise AtlasError(409, "SUBMISSION_EDIT_FORBIDDEN", "当前状态不能修改投稿")
    if item.revision != body.expected_revision:
        raise AtlasError(409, "REVISION_CONFLICT", "投稿已更新", {"currentRevision": item.revision})
    for key, value in body.model_dump(exclude_none=True, exclude={"expected_revision"}).items():
        setattr(item, key, value)
    item.revision += 1
    await session.commit()
    return submission_payload(item)


@router.post("/worlds/{world_id}/submissions/{submission_id}/withdraw")
async def withdraw_submission(submission_id: uuid.UUID, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    item = await session.scalar(select(Submission).where(Submission.id == submission_id, Submission.world_id == access.world.id).with_for_update())
    if not item or item.author_id != access.user.id:
        raise AtlasError(404, "SUBMISSION_NOT_FOUND", "投稿不存在")
    if item.state not in {"character_confirmation", "pending", "revision"}:
        raise AtlasError(409, "SUBMISSION_WITHDRAW_FORBIDDEN", "当前状态不能撤回")
    item.state, item.withdrawn_at, item.revision = "withdrawn", datetime.now(UTC), item.revision + 1
    await session.commit()
    return submission_payload(item)


@router.get("/interaction-confirmations")
async def my_confirmations(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    rows = (await session.execute(select(SubmissionConfirmation, Submission, CharacterProfile).join(Submission, Submission.id == SubmissionConfirmation.submission_id).join(CharacterProfile, CharacterProfile.id == SubmissionConfirmation.character_profile_id).where(SubmissionConfirmation.confirmer_user_id == user.id, SubmissionConfirmation.status == "pending").order_by(SubmissionConfirmation.created_at))).all()
    return {"items": [{"submissionID": str(confirmation.submission_id), "characterProfileID": str(profile.id), "characterObjectID": profile.object_id, "title": item.title, "body": item.body, "status": confirmation.status} for confirmation, item, profile in rows]}


@router.patch("/interaction-confirmations/{submission_id}/{character_profile_id}")
async def decide_confirmation(submission_id: uuid.UUID, character_profile_id: uuid.UUID, body: ConfirmationDecision, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    confirmation = await session.scalar(select(SubmissionConfirmation).where(SubmissionConfirmation.submission_id == submission_id, SubmissionConfirmation.character_profile_id == character_profile_id, SubmissionConfirmation.confirmer_user_id == user.id).with_for_update())
    if not confirmation or confirmation.status != "pending":
        raise AtlasError(404, "CONFIRMATION_NOT_FOUND", "待确认事项不存在")
    item = await session.scalar(select(Submission).where(Submission.id == submission_id).with_for_update())
    assert item
    confirmation.status, confirmation.comment, confirmation.responded_at = body.decision, body.comment, datetime.now(UTC)
    if body.decision == "declined":
        item.state = "revision"
    else:
        remaining = await session.scalar(select(func.count()).select_from(SubmissionConfirmation).where(SubmissionConfirmation.submission_id == submission_id, SubmissionConfirmation.status == "pending", SubmissionConfirmation.character_profile_id != character_profile_id)) or 0
        if remaining == 0:
            item.state = "pending"
    item.revision += 1
    session.add(Notification(recipient_user_id=item.author_id, world_id=item.world_id, type="submission.character-confirmation.result", title=f"角色互动已{ '确认' if body.decision == 'accepted' else '拒绝' }", summary=body.comment, dedupe_key=f"confirmation-result:{submission_id}:{character_profile_id}", action_type="submission", action_target=str(submission_id)))
    await session.commit()
    return {"submissionID": str(item.id), "state": item.state, "decision": body.decision}


@router.post("/worlds/{world_id}/submissions/{submission_id}/review")
async def review_submission(submission_id: uuid.UUID, body: ReviewDecision, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    access.require_manage()
    access.require_write()
    item = await session.scalar(select(Submission).where(Submission.id == submission_id, Submission.world_id == access.world.id).with_for_update())
    if not item:
        raise AtlasError(404, "SUBMISSION_NOT_FOUND", "投稿不存在")
    if item.state != "pending":
        raise AtlasError(409, "SUBMISSION_NOT_REVIEWABLE", "投稿尚未完成共同确认或已经处理")
    item.state = body.decision
    item.revision += 1
    session.add(SubmissionReview(submission_id=item.id, reviewer_id=access.user.id, decision=body.decision, comment=body.comment))
    if body.decision == "accepted":
        object_id = item.target_object_id or f"submission-{item.id}"
        obj = await session.get(WorldObject, (item.world_id, object_id))
        next_revision = (obj.revision if obj else 0) + 1
        payload = {**item.payload, "id": object_id, "title": item.title, "body": item.body, "sourceSubmissionID": str(item.id)}
        if obj:
            obj.title, obj.payload, obj.revision, obj.updated_by = item.title, payload, next_revision, access.user.id
        else:
            obj = WorldObject(world_id=item.world_id, id=object_id, kind=str(item.payload.get("kind", "work")), title=item.title, payload=payload, revision=next_revision, updated_by=access.user.id)
            session.add(obj)
        session.add(WikiRevision(world_id=item.world_id, object_id=object_id, revision=next_revision, title=item.title, payload=payload, author_id=item.author_id))
        canvas = await session.scalar(select(CanvasDocument).where(CanvasDocument.world_id == item.world_id).with_for_update())
        if canvas:
            document, objects = dict(canvas.document), list(canvas.document.get("objects", []))
            index = next((i for i, entry in enumerate(objects) if str(entry.get("id")) == object_id), None)
            if index is None: objects.append(payload)
            else: objects[index] = {**objects[index], **payload}
            document["objects"] = objects
            canvas.document, canvas.revision, canvas.updated_by = document, canvas.revision + 1, access.user.id
            session.add(CanvasRevision(world_id=item.world_id, revision=canvas.revision, document=document, author_id=item.author_id))
        sequence = (await session.scalar(select(func.count()).select_from(ContributionEvent).where(ContributionEvent.world_id == item.world_id, ContributionEvent.user_id == item.author_id, ContributionEvent.target_id == object_id))) or 0
        session.add(ContributionEvent(world_id=item.world_id, user_id=item.author_id, module=body.contribution_module, target_id=object_id, sequence_for_target=min(sequence + 1, 4), scale_points=body.scale_points, completion_points=body.completion_points, specialty_points=body.specialty_points, bonus_points=body.bonus_points, is_polished=body.is_polished, is_seasonal=body.is_seasonal, source_type="submission", source_id=str(item.id)))
    session.add(Notification(recipient_user_id=item.author_id, world_id=item.world_id, type="submission.review.result", title=f"投稿审核：{body.decision}", summary=body.comment, dedupe_key=f"submission-review:{item.id}:{item.revision}", action_type="submission", action_target=str(item.id)))
    session.add(AuditEvent(actor_id=access.user.id, world_id=item.world_id, action=f"submission.review.{body.decision}", target_type="submission", target_id=str(item.id)))
    await session.commit()
    return submission_payload(item)


@router.get("/worlds/{world_id}/contributions")
async def contributions(access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    events = (await session.scalars(select(ContributionEvent).where(ContributionEvent.world_id == access.world.id, ContributionEvent.is_voided.is_(False)).order_by(ContributionEvent.created_at))).all()
    coefficients = [1.0, 0.7, 0.5, 0.3]
    totals: dict[str, dict] = {}
    for event in events:
        base = float(event.scale_points) + float(event.completion_points) + float(event.specialty_points)
        score = base * coefficients[max(0, min(event.sequence_for_target - 1, 3))] + float(event.bonus_points)
        if event.is_polished: score *= 1.5
        if event.is_seasonal: score *= 2
        key = str(event.user_id)
        aggregate = totals.setdefault(key, {"userID": key, "score": 0.0, "modules": {}})
        aggregate["score"] += score
        aggregate["modules"][event.module] = aggregate["modules"].get(event.module, 0.0) + score
    return {"items": sorted(totals.values(), key=lambda item: item["score"], reverse=True)}

