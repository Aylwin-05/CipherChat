import traceback
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rate_limit import rate_limit
from app.models.user import User
from app.repositories.friend_repository import FriendRepository
from app.repositories.story_repository import StoryRepository
from app.services.story_service import StoryService

router = APIRouter(
    prefix="/stories",
    tags=["Stories"],
)


def _service(db: AsyncSession) -> StoryService:

    from app.repositories.block_repository import BlockRepository
    from app.services.block_service import BlockService

    return StoryService(
        StoryRepository(db),
        FriendRepository(db),
        BlockService(
            BlockRepository(db),
            FriendRepository(db),
        ),
    )


# ==========================================================
# Create Story (24h status update, E2EE media)
# ==========================================================

@router.post(
    "/",
    dependencies=[
        rate_limit("stories.create", 10, 60),
    ],
)
async def create_story(
    file: UploadFile = File(...),
    caption: str = Form(""),
    encrypted: bool = Form(True),
    encrypted_key_sender: str | None = Form(None),
    encrypted_key_receiver: str | None = Form(None),
    nonce: str | None = Form(None),
    wrapped_keys: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        import json

        parsed_keys = []

        if wrapped_keys:
            parsed_keys = json.loads(wrapped_keys)

        story = await _service(db).create_story(
            current_user,
            file,
            caption=caption,
            encrypted=encrypted,
            encrypted_key_sender=encrypted_key_sender,
            encrypted_key_receiver=encrypted_key_receiver,
            nonce=nonce,
            wrapped_keys=parsed_keys,
        )

        return story

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    except Exception:
        traceback.print_exc()
        raise


# ==========================================================
# Feed (my stories + friends' active stories)
# ==========================================================

@router.get(
    "/feed",
    dependencies=[
        rate_limit("stories.feed", 30, 60),
    ],
)
async def story_feed(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _service(db).feed(current_user)


# ==========================================================
# Mark Viewed
# ==========================================================

@router.post(
    "/{story_id}/view",
    dependencies=[
        rate_limit("stories.view", 60, 60),
    ],
)
async def mark_viewed(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _service(db).mark_viewed(
            current_user,
            UUID(story_id),
        )

    except PermissionError as error:
        raise HTTPException(
            status_code=403,
            detail=str(error),
        ) from error

    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error


# ==========================================================
# Story Media (owner + friends only)
# ==========================================================

@router.get("/{story_id}/media")
async def story_media(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        path, media_type = await _service(db).get_media_path(
            current_user,
            UUID(story_id),
        )

        return FileResponse(
            path=path,
            media_type=media_type,
        )

    except PermissionError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error


# ==========================================================
# Delete Story (owner only)
# ==========================================================

@router.delete(
    "/{story_id}",
    dependencies=[
        rate_limit("stories.delete", 20, 60),
    ],
)
async def delete_story(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _service(db).delete_story(
            current_user,
            UUID(story_id),
        )

    except PermissionError as error:
        raise HTTPException(
            status_code=403,
            detail=str(error),
        ) from error

    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error