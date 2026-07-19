async def stop_typing_handler(
    realtime_service,
    conversation_id,
    current_user,
    websocket,
    data,
):
    """
    Handle stop typing event.
    """

    await realtime_service.stop_typing(
        conversation_id,
        current_user,
    )