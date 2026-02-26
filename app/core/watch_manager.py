from app.core.config import settings
from app.services.room_service import RoomManager

# Shared Manager instance for watch_together rooms
watch_manager = RoomManager(getattr(settings, "REMOVE_TIME", 30))
