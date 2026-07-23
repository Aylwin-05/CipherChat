from pathlib import Path
from uuid import UUID, uuid4

import mimetypes
import shutil

from fastapi import HTTPException, UploadFile

from app.core.file_config import (
    IMAGE_DIR,
    VIDEO_DIR,
    AUDIO_DIR,
    VOICE_DIR,
    DOCUMENT_DIR,
    ARCHIVE_DIR,
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    AUDIO_EXTENSIONS,
    VOICE_EXTENSIONS,
    DOCUMENT_EXTENSIONS,
    ARCHIVE_EXTENSIONS,
    MAX_IMAGE_SIZE,
    MAX_VIDEO_SIZE,
    MAX_AUDIO_SIZE,
    MAX_DOCUMENT_SIZE,
    MAX_ARCHIVE_SIZE,
)

from app.models.attachment import Attachment
from app.repositories.attachment_repository import AttachmentRepository


class AttachmentService:
    """
    Handles every file upload inside CipherChat.

    Responsibilities
    ----------------
    ✔ Validate uploads
    ✔ Detect attachment type
    ✔ Generate secure filenames
    ✔ Save files
    ✔ Store metadata

    Future

    ✔ Virus Scan
    ✔ Encryption
    ✔ Thumbnail Generation
    ✔ Cloud Storage
    """

    def __init__(
        self,
        repository: AttachmentRepository,
    ):

        self.repository = repository

    # ==========================================================
    # Detect Attachment Type
    # ==========================================================

    def detect_attachment_type(
        self,
        extension: str,
    ) -> str:

        extension = extension.lower()

        if extension in IMAGE_EXTENSIONS:
            return "image"

        if extension in VIDEO_EXTENSIONS:
            return "video"

        if extension in AUDIO_EXTENSIONS:
            return "audio"

        if extension in VOICE_EXTENSIONS:
            return "voice"

        if extension in DOCUMENT_EXTENSIONS:
            return "document"

        if extension in ARCHIVE_EXTENSIONS:
            return "archive"

        raise HTTPException(
            status_code=400,
            detail="Unsupported file type.",
        )

    # ==========================================================
    # Detect Upload Folder
    # ==========================================================

    def upload_directory(
        self,
        attachment_type: str,
    ) -> Path:

        mapping = {
            "image": IMAGE_DIR,
            "video": VIDEO_DIR,
            "audio": AUDIO_DIR,
            "voice": VOICE_DIR,
            "document": DOCUMENT_DIR,
            "archive": ARCHIVE_DIR,
        }

        return mapping[attachment_type]

    # ==========================================================
    # Max File Size
    # ==========================================================

    def max_allowed_size(
        self,
        attachment_type: str,
    ) -> int:

        mapping = {

            "image": MAX_IMAGE_SIZE,

            "video": MAX_VIDEO_SIZE,

            "audio": MAX_AUDIO_SIZE,

            "voice": MAX_AUDIO_SIZE,

            "document": MAX_DOCUMENT_SIZE,

            "archive": MAX_ARCHIVE_SIZE,
        }

        return mapping[attachment_type]

        # ==========================================================
    # Generate Secure Filename
    # ==========================================================

    def generate_filename(
        self,
        extension: str,
    ) -> str:

        return f"{uuid4().hex}{extension.lower()}"

    # ==========================================================
    # Validate Upload
    # ==========================================================

    async def validate_file(
        self,
        file: UploadFile,
    ) -> tuple[str, str, int]:

        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="Invalid filename.",
            )

        extension = Path(
            file.filename
        ).suffix.lower()

        attachment_type = (
            self.detect_attachment_type(
                extension
            )
        )

        contents = await file.read()

        size = len(contents)

        await file.seek(0)

        max_size = self.max_allowed_size(
            attachment_type
        )

        if size > max_size:

            raise HTTPException(
                status_code=400,
                detail=(
                    f"Maximum allowed size is "
                    f"{max_size // (1024 * 1024)} MB."
                ),
            )

        return (
            extension,
            attachment_type,
            size,
        )

    # ==========================================================
    # Save File To Disk
    # ==========================================================

    async def save_file(
        self,
        file: UploadFile,
        attachment_type: str,
        extension: str,
    ) -> tuple[str, str]:

        filename = self.generate_filename(
            extension
        )

        upload_directory = self.upload_directory(
            attachment_type
        )

        upload_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        destination = (
            upload_directory / filename
        )

        with destination.open("wb") as buffer:

            shutil.copyfileobj(
                file.file,
                buffer,
            )

        return (
            filename,
            str(destination),
        )

    # ==========================================================
    # Guess MIME Type
    # ==========================================================

    def detect_mime_type(
        self,
        filename: str,
    ) -> str:

        mime_type, _ = mimetypes.guess_type(
            filename
        )

        return (
            mime_type
            or "application/octet-stream"
        )
    # ==========================================================
    # Upload Attachment
    # ==========================================================

    async def upload_attachment(
        self,
        message_id: UUID,   
        file: UploadFile,
    ) -> Attachment:

        extension, attachment_type, size = (
            await self.validate_file(file)  
        )

        filename, storage_path = (
            await self.save_file(
                file,
                attachment_type,
                extension,
            )
        )

        mime_type = self.detect_mime_type(
            filename
        )

        attachment = Attachment(
            message_id=message_id,
            original_name=file.filename,
            filename=filename,
            mime_type=mime_type,
            extension=extension,
            attachment_type=attachment_type,
            size=size,
            storage_path=storage_path,
        )

        return await self.repository.create_attachment(
            attachment
        )

    # ==========================================================
    # Get Attachment
    # ==========================================================

    async def get_attachment(
        self,
        attachment_id: UUID,
    ) -> Attachment | None:

        return await self.repository.get_by_id(
            attachment_id
        )

    # ==========================================================
    # Delete Attachment
    # ==========================================================

    async def delete_attachment(
        self,
        attachment_id: UUID,
    ) -> bool:

        attachment = await self.get_attachment(
            attachment_id
        )

        if attachment is None:
            return False

        path = Path(
            attachment.storage_path
        )

        if path.exists():
            path.unlink()

        await self.repository.delete_attachment(
            attachment
        )

        return True
        # ==========================================================
    # Get Attachment File Path
    # ==========================================================

    def get_file_path(
        self,
        attachment: Attachment,
    ) -> Path:
        """
        Returns the physical file path.
        """

        return Path(
            attachment.storage_path
        )

    # ==========================================================
    # Check File Exists
    # ==========================================================

    def file_exists(
        self,
        attachment: Attachment,
    ) -> bool:
        """
        Returns whether the file exists.
        """

        return self.get_file_path(
            attachment
        ).exists()

    # ==========================================================
    # Future Encryption Hook
    # ==========================================================

    async def encrypt_file(
        self,
        attachment: Attachment,
    ):
        """
        Placeholder.

        Phase 2:
        Encrypt uploaded files using
        recipient public keys.
        """

        return attachment

    # ==========================================================
    # Future Decryption Hook
    # ==========================================================

    async def decrypt_file(
        self,
        attachment: Attachment,
    ):
        """
        Placeholder.

        Phase 2:
        Decrypt before download.
        """

        return attachment

    # ==========================================================
    # Future Thumbnail Hook
    # ==========================================================

    async def generate_thumbnail(
        self,
        attachment: Attachment,
    ):
        """
        Placeholder.

        Future support:

        • Images
        • Videos
        • PDFs
        """

        return None

    # ==========================================================
    # Human Readable Size
    # ==========================================================

    def readable_size(
        self,
        size: int,
    ) -> str:

        units = [
            "B",
            "KB",
            "MB",
            "GB",
            "TB",
        ]

        value = float(size)

        for unit in units:

            if value < 1024:

                return f"{value:.2f} {unit}"

            value /= 1024

        return f"{value:.2f} PB"