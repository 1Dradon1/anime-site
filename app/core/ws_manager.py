import asyncio
import json
import logging
from typing import Dict, List
import redis.asyncio as redis
from fastapi import WebSocket
from app.core.config import settings

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        # Local state for tracking active connections on THIS worker
        # room_id -> list of active WebSockets
        self.active_rooms: Dict[str, List[WebSocket]] = {}
        # Redis connection for Pub/Sub
        self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
        # Background task for listening to Redis messages
        self.pubsub_task = None

    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept()
        if room_id not in self.active_rooms:
            self.active_rooms[room_id] = []
            # Start pubsub listening task if not already started
            if not self.pubsub_task:
                self.pubsub_task = asyncio.create_task(self._listen_to_redis())

        self.active_rooms[room_id].append(websocket)
        logger.info(
            f"Client connected to room {room_id}. "
            f"Total: {len(self.active_rooms[room_id])}"
        )

    def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.active_rooms:
            if websocket in self.active_rooms[room_id]:
                self.active_rooms[room_id].remove(websocket)
            if not self.active_rooms[room_id]:
                del self.active_rooms[room_id]
        logger.info(f"Client disconnected from room {room_id}.")

    async def broadcast_to_room_local(self, room_id: str, message: dict):
        """Send message only to clients connected to THIS worker."""
        if room_id in self.active_rooms:
            disconnected_clients = []
            for connection in self.active_rooms[room_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning(
                        f"Failed to send to a client in {room_id}: {e}"
                    )
                    disconnected_clients.append(connection)

            for client in disconnected_clients:
                self.disconnect(client, room_id)

    async def broadcast(self, room_id: str, message: dict):
        """Publish message to Redis to reach ALL workers."""
        channel_name = f"watch:room_events:{room_id}"
        await self.redis.publish(channel_name, json.dumps(message))

    async def _listen_to_redis(self):
        """Background task that listens to the Redis Pub/Sub channels."""
        try:
            pubsub = self.redis.pubsub()
            # We subscribe to a pattern to catch all room events
            await pubsub.psubscribe("watch:room_events:*")
            logger.info("Started Redis Pub/Sub listener for WebSockets.")

            async for message in pubsub.listen():
                if message["type"] == "pmessage":
                    channel = message["channel"]
                    # Extract room_id from channel
                    room_id = channel.split(":")[-1]
                    try:
                        data = json.loads(message["data"])
                        # Broadcast the received message to local clients
                        await self.broadcast_to_room_local(room_id, data)
                    except json.JSONDecodeError:
                        logger.error(f"Failed to decode message on {channel}")
        except Exception as e:
            logger.error(f"Redis Pub/Sub listener error: {e}")
            self.pubsub_task = None


manager = ConnectionManager()
