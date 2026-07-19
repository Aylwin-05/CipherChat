from app.services.realtime_service import RealtimeService


async def message_handler(
    websocket_service,
    conversation_id,
    current_user,
    websocket,
    data,
):
    """
    Handle incoming message event.
    """

    content = data.get(
        "content",
        "",
    ).strip()

    if not content:
        return

    realtime = RealtimeService(
        websocket_service
    )

    await realtime.message(
        conversation_id,
        current_user,
        content,
    )