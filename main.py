from flask import Flask, render_template, request, redirect, abort, session, send_file, send_from_directory, Response, stream_with_context, g
from flask_socketio import SocketIO, send, emit, join_room, leave_room
from flask_mobility import Mobility
from flask_httpauth import HTTPBasicAuth
from getters import *
from fast_download import clear_tmp, fast_download, get_path
import watch_together
import json
from json import load
import config
import os

app = Flask(__name__)
auth = HTTPBasicAuth()

USERS = {
    "user": "user",
}

@auth.verify_password
def verify(username, password):
    return USERS.get(username) == password

@app.before_request
@auth.login_required
def protect_all():
    pass
Mobility(app)
socketio = SocketIO(app)

token = config.KODIK_TOKEN
app.config['SECRET_KEY'] = config.APP_SECRET_KEY

with open("translations.json", 'r', encoding='utf-8') as f:
    # Используется для указания озвучки при скачивании файла
    translations = load(f)

if config.USE_SAVED_DATA or config.SAVE_DATA:
    from cache import Cache
    ch = Cache(config.SAVED_DATA_FILE, config.SAVING_PERIOD, config.CACHE_LIFE_TIME)
ch_save = config.SAVE_DATA
ch_use = config.USE_SAVED_DATA

watch_manager = watch_together.Manager(config.REMOVE_TIME)

# Очистка tmp
clear_tmp()

@app.route('/')
def index():
    return render_template('index.html', is_dark=session['is_dark'] if "is_dark" in session.keys() else False)

@app.route('/', methods=['POST'])
def index_form():
    data = dict(request.form)
    if data.get('shikimori_id') and data.get('shikimori_id').strip():
        return redirect(f"/download/sh/{data['shikimori_id'].strip()}/")
    elif data.get('kinopoisk_id') and data.get('kinopoisk_id').strip():
        return redirect(f"/download/kp/{data['kinopoisk_id'].strip()}/")
    elif data.get('kdk') and data.get('kdk').strip(): # kdk = Kodik
        return redirect(f"/search/kdk/{data['kdk'].strip()}/")
    else:
        return redirect("/")
    
@app.route("/change_theme/", methods=['POST'])
def change_theme():
    # Костыль для смены темы
    if "is_dark" in session.keys():
        session['is_dark'] = not(session['is_dark'])
    else:
        session['is_dark'] = True
    return redirect(request.referrer)

@app.route('/search/<string:db>/<string:query>/')
def search_page(db, query):
    if db == "kdk":
        return render_template('search.html', query=query, is_dark=session['is_dark'] if "is_dark" in session.keys() else False)
    else:
        # Другие базы не поддерживаются (возможно в будущем будут)
        return abort(400)

@app.route('/api/search/stream/<string:db>/<string:query>/')
def search_stream(db, query):
    if db != "kdk":
        return abort(400)
    def generate():
        try:
            for item in stream_search_data(query, token, ch if ch_save or ch_use else None):
                yield f"data: {json.dumps(item)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "event: close\ndata: close\n\n"
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/download/<string:serv>/<string:id>/')
def download_shiki_choose_translation(serv, id):
    """
    Render info page with available translations and metadata for a Shikimori or Kinopoisk item.
    
    Parameters:
        serv (str): Service identifier — "sh" for Shikimori or "kp" for Kinopoisk.
        id (str): Item identifier for the requested title.
    
    Returns:
        A rendered info.html response populated with translations, series count and metadata for the requested item.
        If the external data fetch fails, returns a simple HTML error message indicating no data.
        If `serv` is not "sh" or "kp", aborts with HTTP 400.
    """
    cache_wasnt_used = False
    if serv == "sh":
        if ch_use and ch.is_id("sh"+id) and ch.get_data_by_id("sh"+id)['serial_data'] != {}:
            serial_data = ch.get_data_by_id("sh"+id)['serial_data']
        else:
            try:
                # Получаем данные о наличии переводов от кодика
                serial_data = get_serial_info(id, "shikimori", token)
            except Exception as ex:
                serial_data = {'translations': [], 'top_translations': [], 'etc_translations': [], 'series_count': 0, 'error': True, 'debug_msg': str(ex) if config.DEBUG else None}
        cache_used = False
        if ch_use and ch.is_id("sh"+id):
            # Проверка кеша на наличие данных
            cached = ch.get_data_by_id("sh"+id)
            name = cached['title']
            pic = cached['image']
            score = cached['score']
            dtype = cached['type']
            date = cached['date']
            status = cached['status']
            rating = cached['rating']
            year = cached['year']
            description = cached['description']
            if is_good_quality_image(pic):
                # Проверка что была сохранена картинка в полном качестве
                # (При поиске по шики, выдаются картинки в урезанном качестве)
                cache_used = True
        if not cache_used:
            cache_wasnt_used = True
            try:
                # Попытка получить данные с шики
                data = get_shiki_data(id)
                name = data['title']
                pic = data['image']
                score = data['score']
                dtype = data['type']
                date = data['date']
                status = data['status']
                rating = data['rating']
                year = data['year']
                description = data['description']
            except:
                name = 'Неизвестно'
                pic = config.IMAGE_NOT_FOUND
                score = 'Неизвестно'
                dtype = 'Неизвестно'
                date = 'Неизвестно'
                status = 'Неизвестно'
                rating = 'Неизвестно'
                year = 'Неизвестно'
                description = 'Неизвестно'
                score = 'Неизвестно'
                data = False
            finally:
                if ch_save and not ch.is_id("sh"+id):
                    # Записываем данные в кеш если их там нет
                    ch.add_id("sh"+id, name, pic, score, data['status'] if data else "Неизвестно", 
                              data['date'] if data else "Неизвестно", data['year'] if data else 1970, 
                              data['type'] if data else "Неизвестно", data['rating'] if data else "Неизвестно", 
                              data['description'] if data else '', serial_data=serial_data)
        if ch_use and ch_save and ch.is_id("sh"+id) and ch.get_data_by_id("sh"+id)['serial_data'] == {}:
            ch.add_serial_data("sh"+id, serial_data)
        try:
            if ch_use and ch.is_id("sh"+id) and ch.get_data_by_id("sh"+id)['related'] != []:
                related = ch.get_data_by_id("sh"+id)['related']
            else:
                related = get_related(id, 'shikimori', sequel_first=True)
                ch.add_related("sh"+id, related)
        except:
            related = []
        return render_template('info.html', 
            title=name, image=pic, score=score,
            translations=serial_data['translations'],
            top_translations=serial_data['top_translations'],
            etc_translations=serial_data['etc_translations'],
            series_count=serial_data["series_count"], id=id,
            dtype=dtype, date=date, status=status, rating=rating, related=related,
            description=description, is_shiki=True, cache_wasnt_used=cache_wasnt_used, serv=serv,
            error=serial_data.get('error', False), debug_msg=serial_data.get('debug_msg', None),
            is_dark=session['is_dark'] if "is_dark" in session.keys() else False, is_mobile=g.is_mobile,
            shiki_mirror=config.SHIKIMORI_MIRROR if config.SHIKIMORI_MIRROR else "shikimori.one")
    elif serv == "kp":
        try:
            # Получаем данные о наличии переводов от кодика
            serial_data = get_serial_info(id, "kinopoisk", token)
        except Exception as ex:
            serial_data = {'translations': [], 'series_count': 0, 'error': True, 'debug_msg': str(ex) if config.DEBUG else None}
        return render_template('info.html', 
            title="...", image=config.IMAGE_NOT_FOUND, score="...", translations=serial_data['translations'], series_count=serial_data["series_count"], id=id, 
            dtype="...", date="...", status="...", description='...', is_shiki=False, serv=serv,
            error=serial_data.get('error', False), debug_msg=serial_data.get('debug_msg', None),
            is_dark=session['is_dark'] if "is_dark" in session.keys() else False)
    else:
        return abort(400)

@app.route('/download/<string:serv>/<string:id>/<string:data>/')
def download_choose_seria(serv, id, data):
    data = data.split('-')
    series = int(data[0])
    return render_template('download.html', series=series, backlink=f"/download/{serv}/{id}/",
                           is_dark=session['is_dark'] if "is_dark" in session.keys() else False)

@app.route('/download/<string:serv>/<string:id>/<string:data>/<string:download_type>-<string:quality>-<int:seria>/')
def redirect_to_download(serv, id, data, download_type, quality, seria):
    data = data.split('-')
    translation_id = str(data[1])
    if download_type == 'fast':
        return redirect(f'/fast_download/{serv}-{id}-{seria}-{translation_id}-{quality}-{data[0]}/')
    try:
        if serv == "sh":
            if ch_use and ch.is_seria("sh"+id, translation_id, seria):
                # Получаем данные из кеша (если есть и используется)
                url = ch.get_seria("sh"+id, translation_id, seria)
            else:
                # Получаем данные с сервера
                url = get_download_link(id, "shikimori", seria, translation_id, token)
                if ch_save:
                    # Записываем данные в кеш
                    try:
                        # Попытка записать данные к уже имеющимся данным
                        ch.add_seria("sh"+id, translation_id, seria, url)
                    except KeyError:
                        pass
        elif serv == "kp":
            if ch_use and ch.is_seria("kp"+id, translation_id, seria):
                # Получаем данные из кеша (если есть и используется)
                url = ch.get_seria("kp"+id, translation_id, seria)
            else:
                # Получаем данные с сервера
                url = get_download_link(id, "kinopoisk", seria, translation_id, token)
                if ch_save:
                    # Записываем данные в кеш
                    try:
                        # Попытка записать данные к уже имеющимся данным
                        ch.add_seria("kp"+id, translation_id, seria, url)
                    except KeyError:
                        pass
        else:
            return abort(400)
        translation = translations[translation_id] if translation_id in translations else "Неизвестно"
        if seria == 0:
            return redirect(f"https:{url}{quality}.mp4:Перевод-{translation}:.mp4")
        else:
            return redirect(f"https:{url}{quality}.mp4:Серия-{seria}:Перевод-{translation}:.mp4")
    except Exception as ex:
        return abort(500, f'Exception: {ex}')

@app.route('/download/<string:serv>/<string:id>/<string:data>/watch-<int:num>/')
def redirect_to_player(serv, id, data, num):
    if data[0] == "0":
        return redirect(f'/watch/{serv}/{id}/{data}/0/')
    else:
        return redirect(f'/watch/{serv}/{id}/{data}/{num}/')

@app.route('/watch/<string:serv>/<string:id>/<string:data>/<int:seria>/<string:old_quality>/q-<string:quality>/')
@app.route('/watch/<string:serv>/<string:id>/<string:data>/<int:seria>/<string:old_quality>/<int:timing>/q-<string:quality>/')
def change_watch_quality(serv, id, data, seria, old_quality, quality, timing = None):
    return redirect(f"/watch/{serv}/{id}/{data}/{seria}/{quality}/{str(timing)+'/' if timing else ''}")

@app.route('/watch/<string:serv>/<string:id>/<string:data>/<int:seria>/q-<string:quality>/')
@app.route('/watch/<string:serv>/<string:id>/<string:data>/<int:seria>/q-<string:quality>/<int:timing>/')
def redirect_to_old_type_quality(serv, id, data, seria, quality, timing = 0):
    return redirect(f"/watch/{serv}/{id}/{data}/{seria}/{quality}/{str(timing)+'/' if timing else ''}")

@app.route('/watch/<string:serv>/<string:id>/<string:data>/<int:seria>/')
@app.route('/watch/<string:serv>/<string:id>/<string:data>/<int:seria>/<string:quality>/')
@app.route('/watch/<string:serv>/<string:id>/<string:data>/<int:seria>/<string:quality>/<int:timing>/')
def watch(serv, id, data, seria, quality = "720", timing = 0):
    try:
        data = data.split('-')
        series = int(data[0])
        translation_id = str(data[1])
        title = None
        if serv == "sh":
            id_type = "shikimori"
            if ch_use:
                try:
                    title = ch.get_data_by_id("sh"+id)['title'] if ch.get_data_by_id("sh"+id) else None
                except:
                    title = None
            if ch_use and ch.is_seria("sh"+id, translation_id, seria):
                # Получаем данные из кеша (если есть и используется)
                url = ch.get_seria("sh"+id, translation_id, seria)
            else:
                # Получаем данные с сервера
                url = get_download_link(id, "shikimori", seria, translation_id, token)
                if ch_save and not ch.is_seria("sh"+id, translation_id, seria):
                    # Записываем данные в кеш
                    try:
                        ch.add_seria("sh"+id, translation_id, seria, url)
                    except KeyError:
                        pass
        elif serv == "kp":
            id_type = "kinopoisk"
            if ch_use:
                try:
                    title = ch.get_data_by_id("kp"+id)['title'] if ch.get_data_by_id("kp"+id) else None
                except:
                    title = None
            if ch_use and ch.is_seria("kp"+id, translation_id, seria):
                # Получаем данные из кеша (если есть и используется)
                url = ch.get_seria("kp"+id, translation_id, seria)
            else:
                # Получаем данные с сервера
                url = get_download_link(id, "kinopoisk", seria, translation_id, token)
                if ch_save and not ch.is_seria("kp"+id, translation_id, seria):
                    # Записываем данные в кеш
                    try:
                        ch.add_seria("kp"+id, translation_id, seria, url)
                    except KeyError:
                        pass
        else:
            return abort(400)
        straight_url = f"https:{url}{quality}.mp4" # Прямая ссылка
        url = f"/download/{serv}/{id}/{'-'.join(data)}/old-{quality}-{seria}" # Ссылка на скачивание через этот сервер
        return render_template('watch.html',
            url=url, seria=seria, series=series, id=id, id_type=id_type, data="-".join(data), quality=quality, serv=serv, straight_url=straight_url,
            allow_watch_together=config.ALLOW_WATCH_TOGETHER,
            is_dark=session['is_dark'] if "is_dark" in session.keys() else False,
            timing=timing, title=title)
    except:
        return abort(404)

@app.route('/watch/<string:serv>/<string:id>/<string:data>/<int:seria>/', methods=['POST'])
@app.route('/watch/<string:serv>/<string:id>/<string:data>/<int:seria>/<string:quality>/', methods=['POST'])
def change_seria(serv, id, data, seria, quality=None):
    # Если использовалась форма для изменения серии
    try:
        new_seria = int(dict(request.form)['seria'])
    except:
        return abort(400)
    data = data.split('-')
    series = int(data[0])
    if new_seria > series or new_seria < 1:
        return abort(400, "Данная серия не существует")
    else:
        return redirect(f"/watch/{serv}/{id}/{'-'.join(data)}/{new_seria}{'/'+quality if quality != None else ''}")
    

# Watch Together ===================================================
@app.route('/create_room/', methods=['POST'])
def create_room():
    orig = request.referrer
    data = orig.split("/")
    if len(data) == 9:
        data[8] = 720
        data.append('')
    temp = data[-4].split('-')
    data = {
        'serv': data[-6],
        'id': data[-5],
        'series_count': int(temp[0]),
        'translation_id': temp[1],
        'seria': int(data[-3]),
        'quality': int(data[-2]),
        'pause': False,
        'play_time': 0,
    }
    rid = watch_manager.new_room(data)
    watch_manager.remove_old_rooms()
    return redirect(f"/room/{rid}/")

@app.route('/room/<string:rid>/', methods=["GET"])
def room(rid):
    if not watch_manager.is_room(rid):
        return abort(404)
    rd = watch_manager.get_room_data(rid)
    watch_manager.room_used(rid)
    try:
        id = rd['id']
        seria = rd['seria']
        series = rd['series_count']
        translation_id = str(rd['translation_id'])
        quality = rd['quality']
        if rd['serv'] == "sh":
            id_type = "shikimori"
            if ch_use and ch.is_seria("sh"+id, translation_id, seria):
                # Получаем данные из кеша (если есть и используется)
                url = ch.get_seria("sh"+id, translation_id, seria)
            else:
                # Получаем данные с сервера
                url = get_download_link(id, "shikimori", seria, translation_id, token)
                if ch_save and not ch.is_seria("sh"+id, translation_id, seria):
                    # Записываем данные в кеш
                    try:
                        ch.add_seria("sh"+id, translation_id, seria, url)
                    except KeyError:
                        pass
        elif rd['serv'] == "kp":
            id_type = "kinopoisk"
            if ch_use and ch.is_seria("kp"+id, translation_id, seria):
                # Получаем данные из кеша (если есть и используется)
                url = ch.get_seria("kp"+id, translation_id, seria)
            else:
                # Получаем данные с сервера
                url = get_download_link(id, "kinopoisk", seria, translation_id, token)
                if ch_save and not ch.is_seria("kp"+id, translation_id, seria):
                    # Записываем данные в кеш
                    try:
                        ch.add_seria("kp"+id, translation_id, seria, url)
                    except KeyError:
                        pass
        else:
            return abort(400)
        straight_url = f"https:{url}{quality}.mp4" # Прямая ссылка
        url = f"/download/{rd['serv']}/{id}/{series}-{translation_id}/{quality}-{seria}" # Ссылка на скачивание через этот сервер
        return render_template('room.html',
            url=url, seria=seria, series=series, id=id, id_type=id_type, data=f"{series}-{translation_id}", quality=quality, serv=rd['serv'], straight_url=straight_url,
            start_time=rd['play_time'],
            is_dark=session['is_dark'] if "is_dark" in session.keys() else False)
    except:
        return abort(500)

@app.route('/room/<string:rid>/', methods=["POST"])
def change_room_seria_form(rid):
    data = dict(request.form)['seria']
    rdata = watch_manager.get_room_data(rid)
    if data == '':
        pass
    rdata['seria'] = int(data)
    rdata['play_time'] = 0
    watch_manager.room_used(rid)
    socketio.send({"data": {"status": 'update_page', 'time': 0}}, to=rid)
    return redirect(f"/room/{rid}/")

@app.route('/room/<string:rid>/cs-<int:seria>/')
def change_room_seria(rid, seria):
    if not watch_manager.is_room(rid):
        return abort(400)
    rdata = watch_manager.get_room_data(rid)
    rdata['seria'] = seria
    rdata['play_time'] = 0
    watch_manager.room_used(rid)
    socketio.send({"data": {"status": 'update_page', 'time': 0}}, to=rid)
    return redirect(f"/room/{rid}/")

@app.route('/room/<string:rid>/cq-<int:quality>/')
def change_room_quality(rid, quality):
    if not watch_manager.is_room(rid):
        return abort(400)
    rdata = watch_manager.get_room_data(rid)
    rdata['quality'] = quality
    watch_manager.room_used(rid)
    socketio.send({"data": {"status": 'update_page', 'time': rdata['play_time']}}, to=rid)
    return redirect(f"/room/{rid}/")

@app.route('/fast_download_act/<string:id_type>-<string:id>-<int:seria_num>-<string:translation_id>-<string:quality>/')
@app.route('/fast_download_act/<string:id_type>-<string:id>-<int:seria_num>-<string:translation_id>-<string:quality>-<int:max_series>/')
def fast_download_work(id_type: str, id: str, seria_num: int, translation_id: str, quality: str, max_series: int = 12):
    """
    Generate a fast-download package for a specific title/episode and return it as a downloadable file response.
    
    Parameters:
        id_type (str): Server identifier type (e.g., "sh" or "kp").
        id (str): Resource identifier for the title.
        seria_num (int): Episode number (use 0 for whole-title or non-episodic downloads).
        translation_id (str): Translation/track identifier used to label the file and metadata.
        quality (str): Desired video quality label (e.g., "720", "1080").
        max_series (int): Maximum number of series digits to use when zero-padding episode numbers (default 12).
    
    Returns:
        A Flask response that sends the generated file as an attachment, or an HTTP error response when generation fails.
    """
    translation = translations[translation_id] if translation_id in translations else "Неизвестно"
    add_zeros = len(str(max_series))
    if config.USE_SAVED_DATA and ch.is_id('sh'+id):
        if seria_num != 0:
            fname = str(ch.get_data_by_id('sh'+id)['title'])+'-'+f'Серия-{str(seria_num).zfill(add_zeros)}-Перевод-{translation}-{quality}p'
        else:
            fname = str(ch.get_data_by_id('sh'+id)['title'])+'-'+f'Перевод-{translation}-{quality}p'
        metadata = {
            'title': ch.get_data_by_id('sh'+id)['title']+' - Серия-'+str(seria_num) if seria_num != 0 else ch.get_data_by_id('sh'+id)['title'],
            'year': ch.get_data_by_id('sh'+id)['year'],
            'date': ch.get_data_by_id('sh'+id)['year'],
            'comment': ch.get_data_by_id('sh'+id)['description'],
            'artist': translation,
            'track': seria_num
        }
    else:
        metadata = {}
        fname = f'Перевод-{translation}-{quality}p' if seria_num == 0 else f'Серия-{str(seria_num).zfill(add_zeros)}-Перевод-{translation}-{quality}p'
    if len(fname) > 128: # Ограничение на длину имени файла в винде 255 символов, в линуксе 255 байт (т.е. для кириллицы 128 символов)
        if len(translation) > 100:
            fname = f'{quality}p' if seria_num == 0 else f'Серия-{str(seria_num).zfill(add_zeros)}-{quality}p'
        else:
            fname = f'Перевод-{translation}-{quality}p' if seria_num == 0 else f'Серия-{str(seria_num).zfill(add_zeros)}-Перевод-{translation}-{quality}p'
    # Чистка имени файла от запрещенных символов
    # +=[]:*?;«,./\<>|'пробел'  /\:*?<>|
    fname = fname.replace('\\','-').replace('/', '-').replace(':', '-').replace('*','-').replace('"', '\'') \
        .replace('»', '\'').replace('«', '\'').replace('„', '\'').replace('“', '\'').replace('<', '[') \
        .replace(']', ')').replace('|', '-').replace('--', '-').replace('--', '-')
    try:
        hsh, link = fast_download(id, id_type, seria_num, translation_id, quality, config.KODIK_TOKEN,
                            filename=fname, metadata=metadata)
        if ch_save:
            # Записываем данные в кеш
            try:
                # Попытка записать данные к уже имеющимся данным
                ch.add_seria("kp"+id, translation_id, seria_num, link)
            except KeyError:
                pass
        return send_file(get_path(hsh), as_attachment=True, download_name=fname + '.mp4')
    except ModuleNotFoundError:
        return abort(500, 'Внимание, на сервере не установлен ffmpeg или программа не может получить к нему доступ. Ffmpeg обязателен для использования быстрой загрузки. (Стандартная загрузка работает без ffmpeg)')
    except FileNotFoundError:
        return abort(404, 'Видеофайл не найден, попробуйте сменить качество')

@app.route('/fast_download/<string:id_type>-<string:id>-<int:seria_num>-<string:translation_id>-<string:quality>/')
@app.route('/fast_download/<string:id_type>-<string:id>-<int:seria_num>-<string:translation_id>-<string:quality>-<int:max_series>/')
def fast_download_prepare(id_type: str, id: str, seria_num: int, translation_id: str, quality: str, max_series: int = 12):
    return render_template('fast_download_prepare.html', seria_num=seria_num,
                           url=f'/fast_download_act/{id_type}-{id}-{seria_num}-{translation_id}-{quality}-{max_series}/',
                           past_url=request.referrer if request.referrer else f'/download/{id_type}/{id}/',
                           is_dark=session['is_dark'] if "is_dark" in session.keys() else False)

# =======================================================================
# Sockets ====================================

@socketio.on('join')
def on_join(data):
    join_room(data['rid'])
    if not watch_manager.is_room(data['rid']):
        pass
    watch_manager.room_used(data['rid'])
    return send({'data': {'status': 'loading', 'time': watch_manager.get_room_data(data['rid'])['play_time']}}, to=data['rid'])

@socketio.on('broadcast')
def broadcast(data):
    watch_manager.room_used(data['rid'])
    watch_manager.update_play_time(data['rid'], data['data']['time'])
    return send(data, to=data['rid'])

#  ===========================================
# Shortcuts vvvv

@app.route('/help/')
def help():
    # Заглушка
    """
    Redirects the client to the project's README on GitHub.
    
    Returns:
        A Flask redirect response that points the client to the repository README URL.
    """
    return redirect("https://github.com/1Dradon1/anime-site/blob/main/README.MD")

@app.route('/resources/<string:path>')
def resources(path: str):
    """
    Serve a file from the application's resources directory if it exists; abort with 404 otherwise.
    
    Parameters:
        path (str): Relative path to the resource file within the resources directory. Both Windows-style (backslash) and Unix-style (forward slash) paths are supported.
    
    Returns:
        A Flask response sending the requested file when found; aborts with a 404 error if the file does not exist.
    """
    if os.path.exists(f'resources\\{path}'): # Windows-like
        return send_file(f'resources\\{path}')
    elif os.path.exists(f'resources/{path}'): # Unix
        return send_file(f'resources/{path}')
    else:
        return abort(404)

@app.route('/get_episode/<string:shikimori_id>/<int:seria_num>/<string:translation_id>')
def get_episode(shikimori_id: str, seria_num: int, translation_id: str):
    return get_seria_link(shikimori_id, seria_num, translation_id)

@app.route('/guide')
def guide():
    """
    Render the guide page using the current theme preference.
    
    Returns:
        Response: Rendered HTML for 'guide.html' with `is_dark` set to the session's 'is_dark' value or False if missing.
    """
    return render_template('guide.html', is_dark=session.get('is_dark', False))

@app.route('/download/<string:version>')
def download_file(version: str):
    if version == 'low':
        return send_from_directory("./static/", 'dgnmpv-low-end.zip', as_attachment=True, download_name='dgnmpv-low-end.zip')
    elif version == 'high':
        return send_from_directory("./static/", 'dgnmpv.zip', as_attachment=True, download_name='dgnmpv.zip')

@app.route('/favicon.ico')
def favicon():
    return send_file(config.FAVICON_PATH)

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html', is_dark=session.get('is_dark', False)), 404

@app.errorhandler(500)
def internal_server_error(e):
    import traceback
    debug_msg = traceback.format_exc() if config.DEBUG else None
    return render_template('error.html', is_dark=session.get('is_dark', False), debug_msg=debug_msg), 500

if __name__ == "__main__":
    socketio.run(app, host=config.HOST, port=config.PORT, debug=config.DEBUG, allow_unsafe_werkzeug=True)
    