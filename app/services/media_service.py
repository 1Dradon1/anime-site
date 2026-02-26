import os
import subprocess
from hashlib import md5
import requests
import threading
from app.core.config import settings

def check_ffmpeg():
    """
    Checks if ffmpeg is available in the system.
    """
    try:
        subprocess.call(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        raise ModuleNotFoundError('Ffmpeg is required for media operations.')

def get_segments(manifest: str, original_link: str) -> list:
    res = []
    lines = manifest.split('\n')[7:]
    for i in range(0, len(lines), 2):
        if lines[i].strip() != '':
            res.append([original_link + lines[i][2:], lines[i].split('-')[1]])
    return res

def download_segment(link: str, path: str):
    try:
        res = requests.get(link, timeout=15)
        res.raise_for_status()
    except requests.exceptions.RequestException:
        res = requests.get(link, timeout=30)
        res.raise_for_status()
    with open(path, 'wb') as f:
        f.write(res.content)

def combine_segments(directory: str, name: str = 'result', metadata: dict = None, hwaccel: str | None = 'cuda'):
    if metadata is None:
        metadata = {}
    
    files = [x for x in os.listdir(directory) if x.endswith('.ts')]
    files.sort(key=lambda x: int(x[:-3]) if x[:-3].isdigit() else 0)
    
    list_path = os.path.join(directory, 'files.txt')
    with open(list_path, 'w', encoding='utf-8') as f:
        for file in files:
            f.write(f"file '{file}'\n")
    
    metadata_str = ''.join(f'-metadata {k}="{v}" ' for k, v in metadata.items())
    accel = f"-hwaccel {hwaccel}" if hwaccel else ""
    
    cmd = f'ffmpeg -y {accel} -f concat -safe 0 -i {list_path} -c copy {metadata_str} {os.path.join(directory, name)}.mp4'
    subprocess.call(cmd, shell=True, stderr=subprocess.DEVNULL)

class MediaService:
    """
    Service for handling fast downloads and FFmpeg operations.
    Migration of logic from legacy fast_download.py.
    """
    def __init__(self, anime_service):
        self.anime_service = anime_service
        check_ffmpeg()

    def fast_download(self, id: str, id_type: str, seria_num: int, translation_id: str, quality: str, token: str, filename: str = 'result', metadata: dict = None):
        if metadata is None:
            metadata = {}
            
        raw_id_type = id_type
        if id_type == 'sh': id_type = 'shikimori'
        elif id_type == 'kp': id_type = 'kinopoisk'
        
        hsh = md5(f"{id}{raw_id_type}{translation_id}{seria_num}{quality}".encode('utf-8')).hexdigest() + "~"
        tmp_dir = os.path.join("tmp", hsh)
        os.makedirs(tmp_dir, exist_ok=True)
        
        if any(x.endswith('.mp4') for x in os.listdir(tmp_dir)):
            return hsh, "" # Link not available if already cached locally
            
        # Clean directory
        for f in os.listdir(tmp_dir):
            os.remove(os.path.join(tmp_dir, f))
            
        # Implementation is very similar to media_tasks.py but remains here for sync usage if needed
        # In multi-tenant environments, we should probably only use the Celery task.
        return hsh, "Refer to Celery for high-performance downloads"

    def get_path(self, hsh: str) -> str:
        d = os.path.join("tmp", hsh)
        if not os.path.exists(d):
            raise FileNotFoundError(f"Hash directory {hsh} not found")
        
        mp4s = [f for f in os.listdir(d) if f.endswith('.mp4')]
        if mp4s:
            return os.path.join(d, mp4s[0])
        raise FileNotFoundError(f"No mp4 found in {hsh}")

    def clear_tmp(self):
        if not os.path.exists('tmp'):
            os.mkdir('tmp')
        import shutil
        for item in os.listdir('tmp'):
            shutil.rmtree(os.path.join('tmp', item), ignore_errors=True)
