from uuid import UUID


async def read_handler(
    realtime_service,
    conversation_id,
    current_user,
    websocket,
    data,
):
    """
    Handle message read acknowledgement.
    """

    message_id = data.get("message_id")

    if not message_id:
        return

    await realtime_service.read(
        conversation_id,
        current_user,
        UUID(message_id),
    )