from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from app.core.ws_manager import ConnectionManager
import logging
import json
from app.core.security import get_current_user_ws

router = APIRouter()
manager = ConnectionManager()
logger = logging.getLogger(__name__)


@router.websocket("/ws/room/{rid}")
async def websocket_endpoint(
    websocket: WebSocket, rid: str, user: str = Depends(get_current_user_ws)
):
    await manager.connect(websocket, rid)
    try:
        # Upon connection, fetch current room state from the global manager
        # (Redis later, currently in-memory/sync bridge)
        # Note: Since watch_manager is currently synchronous and global to
        # Flask, we need a bridge.
        # For this step, we will assume room state is managed via our
        # Pub/Sub, but we send an initial "loading" state.

        # We need to get the current play time. For a phased migration, we
        # might just rely on clients to broadcast their time, or fetch from
        # Redis directly if watch_manager is fully migrated.

        # Let's send a join confirmation
        await websocket.send_json({
            "status": "connected",
            "rid": rid
        })

        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            # Message format expected from frontend:
            # {"type": "broadcast", "data": {"status": "update", "time": 1}}

            if message.get("type") == "broadcast":
                # Add rid to the message payload so other clients know
                payload = message.get("data", {})
                payload["rid"] = rid
                # Publish to Redis
                await manager.broadcast(rid, payload)
    except WebSocketDisconnect:
        manager.disconnect(websocket, rid)
        logger.info(f"Client disconnected from room {rid}")
    except Exception as e:
        logger.error(f"WebSocket error in room {rid}: {e}")
        manager.disconnect(websocket, rid)
