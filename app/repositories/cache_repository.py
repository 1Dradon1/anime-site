import json
import logging
import redis
from time import time

logger = logging.getLogger(__name__)


class CacheRepository:
    """
    Redis-based implementation replacing the legacy in-memory cache.json.
    Namespaces:
      cache:title:{id} -> JSON string with title metadata
    """
    def __init__(self, redis_url: str, cache_life_time_days: int = 3):
        self.redis_url = redis_url
        self.life_time_seconds = cache_life_time_days * 24 * 60 * 60
        self.client = redis.from_url(redis_url, decode_responses=True)
        try:
            self.client.ping()
            logger.info(f"[CACHE] Connected to Redis at {redis_url}")
        except redis.ConnectionError as e:
            logger.error(f"[CACHE] Failed to connect to Redis: {e}")

    def _get_key(self, id: str) -> str:
        return f"cache:title:{id}"

    def get_data_by_id(self, id: str) -> dict:
        data_str = self.client.get(self._get_key(id))
        if data_str:
            return json.loads(data_str)
        raise KeyError("Id not found")

    def get_seria(self, id: str, translation_id: str, seria_num: int) -> str:
        data = self.get_data_by_id(id)
        # Type conversions for robust retrieval
        translation_id = str(translation_id)
        seria_num = str(seria_num)

        if translation_id in data.get('urls', {}) and \
                seria_num in data['urls'][translation_id]:
            return data['urls'][translation_id][seria_num]
        raise KeyError("Id not found")

    def add_seria(
        self, id: str, translation_id: str, seria_num: int, url: str
    ):
        translation_id = str(translation_id)
        seria_num = str(seria_num)

        try:
            data = self.get_data_by_id(id)
        except KeyError:
            raise KeyError("Id not found")

        if translation_id not in data.get('urls', {}):
            if 'urls' not in data:
                data['urls'] = {}
            data['urls'][translation_id] = {}

        data['urls'][translation_id][seria_num] = url
        self._save(id, data)

    def add_id(
        self, id: str, title: str, img_url: str, score: str, status: str,
        dates: str, year: int, ttype: str, mpaa_rating: str = 'Неизвестно',
        description: str = '', related: list = None, serial_data: dict = None
    ):
        if related is None:
            related = []
        if serial_data is None:
            serial_data = {}

        data = {
            "title": title,
            "image": img_url,
            "score": score,
            "status": status,
            "date": dates,
            "year": str(year),
            "type": ttype,
            "rating": mpaa_rating,
            "description": description,
            "last_updated": time(),
            "related": related,
            "serial_data": serial_data,
            "urls": {}
        }
        self._save(id, data)

    def add_translation(self, id: str, translation_id: str):
        translation_id = str(translation_id)
        try:
            data = self.get_data_by_id(id)
            if 'urls' not in data:
                data['urls'] = {}
            if translation_id not in data['urls']:
                data['urls'][translation_id] = {}
            self._save(id, data)
        except KeyError:
            raise KeyError("Id not found")

    def add_serial_data(self, id: str, serial_data: dict):
        try:
            data = self.get_data_by_id(id)
            data['serial_data'] = serial_data
            self._save(id, data)
        except KeyError:
            raise KeyError("Id not found")

    def add_related(self, id: str, related: list):
        try:
            data = self.get_data_by_id(id)
            data['related'] = related
            self._save(id, data)
        except KeyError:
            raise KeyError("Id not found")

    def change_image(self, id: str, image_src: str):
        try:
            data = self.get_data_by_id(id)
            data['image'] = image_src
            self._save(id, data)
        except KeyError:
            pass

    def is_id(self, id: str) -> bool:
        return self.client.exists(self._get_key(id)) > 0

    def is_translation(self, id: str, translation_id: str) -> bool:
        translation_id = str(translation_id)
        if not self.is_id(id):
            return False
        try:
            data = self.get_data_by_id(id)
            return translation_id in data.get('urls', {})
        except KeyError:
            return False

    def is_seria(self, id: str, translation_id: str, seria_num: int) -> bool:
        translation_id = str(translation_id)
        seria_num = str(seria_num)
        if not self.is_translation(id, translation_id):
            return False
        try:
            data = self.get_data_by_id(id)
            return seria_num in data.get('urls', {}).get(translation_id, {})
        except KeyError:
            return False

    def _save(self, id: str, data: dict):
        key = self._get_key(id)
        val = json.dumps(data, ensure_ascii=False)
        self.client.set(key, val, ex=self.life_time_seconds)
