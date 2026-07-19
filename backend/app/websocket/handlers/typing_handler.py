async def typing_handler(
    realtime_service,
    conversation_id,
    current_user,
    websocket,
    data,
):
    """
    Handle typing event.
    """

    await realtime_service.typing(
        conversation_id,
        current_user,
    )