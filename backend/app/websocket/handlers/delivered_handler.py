from uuid import UUID


async def delivered_handler(
    realtime_service,
    conversation_id,
    current_user,
    websocket,
    data,
):
    """
    Handle message delivered acknowledgement.
    """

    message_id = data.get("message_id")

    if not message_id:
        return

    await realtime_service.delivered(
        conversation_id,
        current_user,
        UUID(message_id),
    )