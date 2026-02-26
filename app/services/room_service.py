from time import time
from hashlib import md5
import json
import redis
from app.core.config import settings

class RoomManager:
    """
    Manages "Watch Together" rooms using Redis for state storage.
    Migration of the legacy Manager class from root watch_together.py.
    """
    def __init__(self, remove_time_minutes: int):
        self.remove_time_seconds = remove_time_minutes * 60
        self.client = redis.from_url(settings.REDIS_URL, decode_responses=True)

    def _get_key(self, id: str) -> str:
        return f"watch:room:{id}"

    def new_room(self, data: dict) -> str:
        now = time()
        hsh = md5(str(now).encode('utf-8')).hexdigest()
        data['last_used'] = now
        
        self.update_room(hsh, data)
        return hsh
    
    def is_room(self, id: str) -> bool:
        return self.client.exists(self._get_key(id)) > 0
    
    def get_room_data(self, id: str) -> dict:
        data_str = self.client.get(self._get_key(id))
        if data_str:
            return json.loads(data_str)
        raise KeyError(f"Room {id} not found")

    def update_room(self, id: str, data: dict):
        data['last_used'] = time()
        self.client.set(self._get_key(id), json.dumps(data, ensure_ascii=False), ex=self.remove_time_seconds)

    def update_play_time(self, id: str, play_time: float):
        try:
            data = self.get_room_data(id)
            data['play_time'] = play_time
            self.update_room(id, data)
        except KeyError:
            pass

    def broadcast(self, id: str, data: dict):
        channel_name = f"watch:room_events:{id}"
        self.client.publish(channel_name, json.dumps(data))

    def room_used(self, id: str):
        try:
            data = self.get_room_data(id)
            self.update_room(id, data)
        except KeyError:
            pass
