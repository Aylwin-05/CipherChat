import traceback
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rate_limit import rate_limit

from app.models.user import User

from app.repositories.conversation_repository import (
    ConversationRepository,
)
from app.repositories.friend_repository import (
    FriendRepository,
)
from app.repositories.message_repository import (
    MessageRepository,
)

from app.schemas.conversation import (
    AddGroupMembersRequest,
    ConversationResponse,
    CreateConversationRequest,
    CreateGroupRequest,
    UpdateConversationSettingsRequest,
)

from app.services.conversation_service import (
    ConversationService,
)

router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"],
)


# ==========================================================
# Open/Create Conversation
# ==========================================================

@router.post(
    "/private",
    response_model=ConversationResponse,
    dependencies=[
        rate_limit("conversations.create", 30, 60),
    ],
)
async def create_private_conversation(
    request: CreateConversationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        conversation_repository = ConversationRepository(db)
        message_repository = MessageRepository(db)

        service = ConversationService(
            conversation_repository,
            message_repository,
        )

        
        conversation = await service.get_or_create_private_conversation(
            current_user,
            request.user_id,
        )

        
        await db.commit()

        
        await db.refresh(conversation)

        
        other_user = await conversation_repository.get_other_user(
            conversation.id,
            current_user.id,
        )

        
        
        last_message = await message_repository.get_last_message(
            conversation.id,
            current_user.id,
        )

        
        
        return {
            "id": conversation.id,
            "updated_at": conversation.updated_at,
            "other_user": other_user,
            "last_message": (
                {
                    "ciphertext": last_message.ciphertext,
                    "message_type": last_message.message_type,
                    "created_at": last_message.created_at,
                }
                if last_message
                else None
            ),
            "disappear_after_seconds":
                conversation.disappear_after_seconds,
            "delete_requested_by":
                str(conversation.delete_requested_by)
                if conversation.delete_requested_by
                else None,
            "delete_requested_at":
                conversation.delete_requested_at.isoformat()
                if conversation.delete_requested_at
                else None,
        }

    except Exception:
        traceback.print_exc()
        raise

# ==========================================================
# Update Settings (pin / archive / mute)
# ==========================================================

@router.patch("/{conversation_id}")
async def update_conversation_settings(
    conversation_id: str,
    request: UpdateConversationSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID

    try:
        conversation_repository = ConversationRepository(db)
        message_repository = MessageRepository(db)

        service = ConversationService(
            conversation_repository,
            message_repository,
        )

        # Only apply the fields the client actually sent, so an
        # explicit `muted_until: null` can clear an existing mute.
        payload = {}

        if "is_pinned" in request.model_fields_set:
            payload["is_pinned"] = bool(request.is_pinned)

        if "is_archived" in request.model_fields_set:
            payload["is_archived"] = bool(request.is_archived)

        if "muted_until" in request.model_fields_set:
            payload["muted_until"] = request.muted_until

        if "disappear_after_seconds" in request.model_fields_set:
            payload["disappear_after_seconds"] = (
                request.disappear_after_seconds
            )

        settings = await service.update_settings(
            current_user,
            UUID(conversation_id),
            **payload,
        )

        await db.commit()

        return {
            "id": conversation_id,
            **settings,
        }

    except PermissionError as error:
        raise HTTPException(
            status_code=403,
            detail=str(error),
        ) from error

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail="Invalid conversation id.",
        ) from error

# ==========================================================
# My Conversations
# ==========================================================

@router.get("/")
async def my_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conversation_repository = ConversationRepository(db)
    message_repository = MessageRepository(db)

    service = ConversationService(
        conversation_repository,
        message_repository,
    )

    return await service.my_conversations(
        current_user
    )

# ==========================================================
# Create Group
# ==========================================================

@router.post(
    "/group",
    response_model=ConversationResponse,
    dependencies=[
        rate_limit("conversations.create", 30, 60),
    ],
)
async def create_group(
    request: CreateGroupRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        conversation_repository = ConversationRepository(db)
        message_repository = MessageRepository(db)

        service = ConversationService(
            conversation_repository,
            message_repository,
            FriendRepository(db),
        )

        conversation = await service.create_group(
            current_user,
            request.name,
            request.member_ids,
        )

        await db.commit()

        await db.refresh(conversation)

        participant_count = (
            await conversation_repository.get_participant_count(
                conversation.id
            )
        )

        return {
            "id": conversation.id,
            "updated_at": conversation.updated_at,
            "conversation_type": conversation.conversation_type,
            "name": conversation.name,
            "participant_count": participant_count,
            "other_user": None,
            "last_message": None,
            "disappear_after_seconds":
                conversation.disappear_after_seconds,
            "delete_requested_by": None,
            "delete_requested_at": None,
        }

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

# ==========================================================
# Group Detail
# ==========================================================

@router.get(
    "/{conversation_id}",
    dependencies=[
        rate_limit("conversations.detail", 60, 60),
    ],
)
async def group_detail(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        conversation_repository = ConversationRepository(db)
        message_repository = MessageRepository(db)

        service = ConversationService(
            conversation_repository,
            message_repository,
        )

        return await service.get_group_detail(
            current_user,
            UUID(conversation_id),
        )

    except PermissionError as error:
        raise HTTPException(
            status_code=403,
            detail=str(error),
        ) from error

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

# ==========================================================
# Add Group Members (admin only)
# ==========================================================

@router.post(
    "/{conversation_id}/group/add",
    dependencies=[
        rate_limit("conversations.group", 20, 60),
    ],
)
async def add_group_members(
    conversation_id: str,
    request: AddGroupMembersRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        conversation_repository = ConversationRepository(db)
        message_repository = MessageRepository(db)

        service = ConversationService(
            conversation_repository,
            message_repository,
            FriendRepository(db),
        )

        return await service.add_group_members(
            current_user,
            UUID(conversation_id),
            request.member_ids,
        )

    except PermissionError as error:
        raise HTTPException(
            status_code=403,
            detail=str(error),
        ) from error

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

# ==========================================================
# Leave Group
# ==========================================================

@router.post(
    "/{conversation_id}/group/leave",
    dependencies=[
        rate_limit("conversations.group", 20, 60),
    ],
)
async def leave_group(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        conversation_repository = ConversationRepository(db)
        message_repository = MessageRepository(db)

        service = ConversationService(
            conversation_repository,
            message_repository,
        )

        return await service.leave_group(
            current_user,
            UUID(conversation_id),
        )

    except PermissionError as error:
        raise HTTPException(
            status_code=403,
            detail=str(error),
        ) from error

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

# ==========================================================
# Two-Party Conversation Deletion
#
# request:  User 1 presses "delete chat" -> pending request,
#           the other participant gets a real-time popup.
# confirm:  User 2 confirms -> BOTH consented, the server
#           purges all messages + attachments (rows and
#           physical files) + the conversation itself.
# cancel:   Either participant aborts a pending request.
# ==========================================================

@router.post(
    "/{conversation_id}/delete-request",
    dependencies=[
        rate_limit("conversations.delete", 10, 60),
    ],
)
async def request_conversation_delete(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        conversation_repository = ConversationRepository(db)
        message_repository = MessageRepository(db)

        service = ConversationService(
            conversation_repository,
            message_repository,
        )

        return await service.request_conversation_delete(
            current_user,
            UUID(conversation_id),
        )

    except PermissionError as error:
        raise HTTPException(
            status_code=403,
            detail=str(error),
        ) from error

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error


@router.post(
    "/{conversation_id}/delete-confirm",
    dependencies=[
        rate_limit("conversations.delete", 10, 60),
    ],
)
async def confirm_conversation_delete(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        conversation_repository = ConversationRepository(db)
        message_repository = MessageRepository(db)

        service = ConversationService(
            conversation_repository,
            message_repository,
        )

        return await service.confirm_conversation_delete(
            current_user,
            UUID(conversation_id),
        )

    except PermissionError as error:
        raise HTTPException(
            status_code=403,
            detail=str(error),
        ) from error

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error


@router.post(
    "/{conversation_id}/delete-cancel",
    dependencies=[
        rate_limit("conversations.delete", 10, 60),
    ],
)
async def cancel_conversation_delete(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        conversation_repository = ConversationRepository(db)
        message_repository = MessageRepository(db)

        service = ConversationService(
            conversation_repository,
            message_repository,
        )

        return await service.cancel_conversation_delete(
            current_user,
            UUID(conversation_id),
        )

    except PermissionError as error:
        raise HTTPException(
            status_code=403,
            detail=str(error),
        ) from error

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error