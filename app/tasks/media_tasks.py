import os
import subprocess
import requests
import threading
from hashlib import md5
from app.core.celery_app import celery_app
# Placeholder for moving getters logic into service
# We will instantiate a service inside the task or use a global one
import logging

logger = logging.getLogger(__name__)


# Reused functions from fast_download.py but without blocking web workers


def check_ffmpeg():
    try:
        subprocess.call(
            ['ffmpeg', '-version'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        raise ModuleNotFoundError(
            'Ffmpeg is required to use fast download. Error: ' + str(e)
        )


def get_segments(manifest: str, original_link: str) -> list[tuple[str, str]]:
    res = []
    lines = manifest.split("\n")
    # m3u8 playlists usually start listing segments after metadata headers
    for i, line in enumerate(lines):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # The structure is #EXTINF:...\n<segment_url>
        res.append((
            original_link + '/' + line.lstrip('./'),
            f"seg_{i}"
        ))
    return res


def download_segment(link: str, path: str):
    try:
        res = requests.get(link, timeout=15)
        res.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to fetch segment {link}: {e}")
        # Retry once
        res = requests.get(link, timeout=30)
        res.raise_for_status()

    with open(path, "wb") as f:
        f.write(res.content)


def combine_segments(
    directory: str,
    name: str = 'result',
    metadata: dict = None,
    hwaccel: str | None = 'cuda'
):
    if metadata is None:
        metadata = {}

    files = [x for x in os.listdir(directory) if x.endswith('.ts')]

    # Needs sorting based on segment index or name
    # We assigned name "seg_i.ts", so we sort by the integer i
    files.sort(
        key=lambda x: int(x.split('_')[1].split('.')[0]) if '_' in x else 0
    )

    list_file_path = os.path.join(directory, 'files.txt')
    with open(list_file_path, 'w', encoding='utf-8') as f:
        for file in files:
            # ffmpeg concat demuxer requires 'file path/to/file.ts'
            f.write(f"file '{file}'\n")

    metadata_args = []
    for k, v in metadata.items():
        metadata_args.extend(['-metadata', f'{k}={v}'])

    hwaccel_args = ['-hwaccel', hwaccel] if hwaccel else []
    output_path = os.path.join(directory, f"{name}.mp4")

    cmd = (
        ['ffmpeg', '-y'] + hwaccel_args +
        ['-f', 'concat', '-safe', '0', '-i', list_file_path, '-c', 'copy'] +
        metadata_args + [output_path]
    )

    logger.info(f"Running ffmpeg: {' '.join(cmd)}")
    result = subprocess.call(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    if result != 0:
        raise RuntimeError(f"ffmpeg failed with exit code {result}")


@celery_app.task(bind=True, max_retries=2, soft_time_limit=540, time_limit=600)
def download_and_concat_task(
    self, id: str, id_type: str, seria_num: int, translation_id: str,
    quality: str, token: str, filename: str = 'result', metadata: dict = None
):
    """
    Celery task that replaces the synchronous fast_download function.
    Downloads M3U8 segments in parallel threads, concats with ffmpeg,
    and returns the hash.
    """
    if metadata is None:
        metadata = {}

    check_ffmpeg()

    # Use standard hash generation identical to fast_download
    raw_hash_str = str(
        id + id_type + translation_id + str(seria_num) + quality
    )
    hsh = md5(raw_hash_str.encode('utf-8')).hexdigest() + "~"

    # We will safely use tmp/hsh/ relative to the CWD
    base_dir = os.path.abspath("tmp")
    task_dir = os.path.join(base_dir, hsh)

    os.makedirs(task_dir, exist_ok=True)

    # Check if a completed file already exists
    existing_mp4s = [x for x in os.listdir(task_dir) if x.endswith(".mp4")]
    if existing_mp4s:
        logger.info(f"Target exists for hash {hsh}. Skipping download.")
        return {"status": "SUCCESS", "hash": hsh, "filename": existing_mp4s[0]}

    # Clear lingering temp segments just in case
    for item in os.listdir(task_dir):
        os.remove(os.path.join(task_dir, item))

    # Normalize ID type for getters
    if id_type == "sh":
        api_id_type = "shikimori"
    elif id_type == "kp":
        api_id_type = "kinopoisk"
    else:
        api_id_type = id_type

    # Get stream URL
    from app.services.anime_service import AnimeService
    anime_service = AnimeService()
    link = anime_service.get_seria_link(id, seria_num, translation_id)
    manifest_url = f"https:{link}{quality}.mp4:hls:manifest.m3u8"

    logger.info(f"Fetching m3u8 manifest: {manifest_url}")
    res = requests.get(manifest_url, timeout=15)
    res.raise_for_status()
    manifest = res.text
    segments = get_segments(manifest, f"https:{link}")

    logger.info(f"Downloading {len(segments)} segments...")
    threads = []

    # Download Segments (parallel threads)
    for seg_url, seg_name in segments:
        seg_path = os.path.join(task_dir, f"{seg_name}.ts")
        t = threading.Thread(target=download_segment, args=(seg_url, seg_path))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    logger.info("Combining segments via ffmpeg...")
    safe_filename = filename.replace(' ', '-')
    combine_segments(
        task_dir, name=safe_filename, metadata=metadata, hwaccel='cuda'
    )

    # Cleanup .ts files
    for f in os.listdir(task_dir):
        if f.endswith('.ts') or f == 'files.txt':
            os.remove(os.path.join(task_dir, f))

    return {
        'status': 'SUCCESS',
        'hash': hsh,
        'filename': f"{safe_filename}.mp4"
    }
