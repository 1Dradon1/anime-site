from anime_parsers_ru import KodikParser, ShikimoriParser, errors
import requests
from time import sleep, time
import re
import logging
from app.core.config import settings
from app.repositories.cache_repository import CacheRepository

logger = logging.getLogger(__name__)

class AnimeService:
    """
    Handles interactions with anime data providers (Kodik, Shikimori).
    Migration of logic from legacy getters.py.
    """
    def __init__(self, cache_repo: CacheRepository = None):
        self.cache = cache_repo
        
        # Initialize Kodik parser with settings
        try:
            val_token = bool(settings.KODIK_TOKEN)
            self.kodik = KodikParser(
                token=settings.KODIK_TOKEN, 
                use_lxml=settings.USE_LXML, 
                validate_token=val_token
            )
        except errors.TokenError:
            logger.warning("Kodik token validation failed. Falling back to Shikimori-only search.")
            self.kodik = KodikParser(use_lxml=settings.USE_LXML, validate_token=False)

        self.shiki = ShikimoriParser(
            use_lxml=settings.USE_LXML, 
            mirror=settings.SHIKIMORI_MIRROR
        )

        self.priority_order = [
            "Дублированный", "ТО Дубляжная", "Studio Band", "AniLiberty (AniLibria)",
            "AniLibria.TV", "JAM", "Dream Cast", "SHIZA Project", "Reanimedia", "AnimeVost"
        ]
        self.priority_index = {name: i for i, name in enumerate(self.priority_order)}

    def get_seria_link(self, item_id: str, seria_num: int, translation_id: str, id_type: str = "shikimori"):
        return self.kodik.get_m3u8_playlist_link(
            id=item_id,
            id_type=id_type,
            seria_num=seria_num,
            translation_id=translation_id,
            quality=720
        )

    def get_serial_info(self, id: str, id_type: str) -> dict:
        data = self.kodik.get_info(id, id_type)
        try:
            priority_list, normal_list, subs = self._format_translations(data["translations"])
            data["translations"] = priority_list + normal_list + subs
            data["top_translations"] = priority_list
            data["etc_translations"] = normal_list + subs
        except Exception:
            data["top_translations"] = data.get("translations", [])
            data["etc_translations"] = []
        return data

    def _format_translations(self, translations):
        priority_list = []
        normal_list = []
        subs = []
        for t in translations:
            if t.get("type") != "Озвучка":
                subs.append(t)
                continue
            name = t.get("name", "")
            match = re.search(r'\((\d+)', t["name"])
            t["series_count"] = int(match.group(1)) if match else 0
            if any(name.startswith(p) for p in self.priority_order):
                priority_list.append(t)
            else:
                normal_list.append(t)

        priority_list.sort(key=self._sort_key)
        normal_list.sort(key=self._sort_key)
        subs.sort(key=self._sort_key)
        return priority_list, normal_list, subs

    def _sort_key(self, item):
        name = item.get("name", "")
        series_count = item.get("series_count", 0)
        for p_name in self.priority_order:
            if name.startswith(p_name):
                priority = self.priority_index[p_name]
                break
        else:
            priority = float('inf')
        return (-series_count, priority, name)

    def stream_search_data(self, search_query: str, search_engine: str):
        if search_engine == "kdk":
            search_res = self.kodik.search(search_query)
        else:
            search_res = self.shiki.search(search_query)

        used_ids = []
        for item in search_res:
            shiki_id = item.get('shikimori_id')
            if shiki_id and shiki_id not in used_ids:
                cache_id = f"sh{shiki_id}"
                if self.cache and self.cache.is_id(cache_id):
                    ser_data = self.cache.get_data_by_id(cache_id)
                else:
                    try:
                        ser_data = self.get_shiki_data(shiki_id)
                        if self.cache:
                            self.cache.add_id(
                                cache_id, ser_data['title'], ser_data['image'], 
                                ser_data['score'], ser_data['status'], ser_data['date'], 
                                ser_data['year'], ser_data['type'], ser_data['rating'], 
                                ser_data['description']
                            )
                    except RuntimeWarning:
                        continue
                
                yield {
                    'category': 'anime',
                    'image': ser_data['image'] or settings.IMAGE_NOT_FOUND,
                    'id': shiki_id,
                    'type': ser_data['type'],
                    'date': ser_data['date'],
                    'title': item['title'],
                    'status': ser_data['status'],
                    'year': ser_data['year'],
                    'description': ser_data['description']
                }
                used_ids.append(shiki_id)
            
            kp_id = item.get('kinopoisk_id')
            if kp_id and (not shiki_id) and kp_id not in used_ids:
                type_map = {
                    "foreign-movie": "Иностранный фильм",
                    "foreign-serial": "Иностранный сериал",
                    "russian-movie": "Русский фильм",
                    "russian-serial": "Русский сериал"
                }
                yield {
                    'category': 'other',
                    "id": kp_id,
                    "title": item['title'],
                    "type": type_map.get(item['type'], item['type']),
                    "date": item['year']
                }
                used_ids.append(kp_id)

    def get_shiki_data(self, id: str, retries: int = 3):
        if retries <= 0:
            raise RuntimeWarning(f"Max retries getting data exceeded. Id: {id}")
        try:
            data = self.shiki.anime_info(self.shiki.link_by_id(id))
            return {
                'title': data['title'],
                'image': data['picture'],
                'type': data['type'],
                'date': data['dates'],
                'status': data['status'],
                'score': data['score'],
                'rating': data['rating'],
                'description': data['description'],
                'year': data['dates'][-7:-3] if data.get('dates') and data['dates'][-7:-3].isdigit() else 1970
            }
        except errors.AgeRestricted:
            return self._handle_nsfw(id)
        except errors.TooManyRequests:
            sleep(0.5)
            return self.get_shiki_data(id, retries - 1)
        except errors.NoResults:
            raise RuntimeWarning

    def _handle_nsfw(self, id: str):
        if settings.ALLOW_NSFW:
            try:
                d = self.shiki.deep_anime_info(id, [
                    'russian', 'kind', 'rating', 'status', 'releasedOn { year, date }', 
                    'score', 'poster { originalUrl }', 'description'
                ])
                return {
                    'title': d['russian'], 'image': d['poster']['originalUrl'],
                    'type': d['kind'], 'status': d['status'], 
                    'year': d['releasedOn']['year'] or 1970, 'date': d['releasedOn']['date'],
                    'score': d['score'], 'rating': d['rating'], 'description': d['description']
                }
            except Exception:
                pass
        return {
            'title': f"18+ (Shikimori id: {id})", 'image': settings.IMAGE_AGE_RESTRICTED,
            'type': "Неизвестно", 'status': "Неизвестно", 'date': "Неизвестно",
            'score': "Неизвестно", 'rating': '18+', 'year': 1970, 'description': 'Неизвестно'
        }

    def get_related(self, id: str, id_type: str, sequel_first: bool = False) -> list:
        id_type = 'shikimori' if id_type == 'sh' else id_type
        if id_type != 'shikimori':
            raise ValueError('Only shikimori id is supported')
        
        link = self.shiki.link_by_id(id)
        data = self.shiki.additional_anime_info(link)['related']
        res = []
        for x in data:
            if not x['date']: x['date'] = 'Неизвестно'
            if x['type'] in ['Манга', 'Ранобэ', 'Клип']:
                x['internal_link'] = x['url']
            else:
                sid = self.shiki.id_by_link(x['url'])
                x['internal_link'] = f'/download/sh/{sid}/'
            res.append(x)
        
        if sequel_first:
            return sorted(res, key=lambda x: 0 if x["relation"] == 'Продолжение' else (1 if x["relation"] == 'Предыстория' else 2))
        return res
