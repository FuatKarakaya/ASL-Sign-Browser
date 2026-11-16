"""Download exact top-200 references and verify every MP4 by decoding it fully.

One-time setup: python -m pip install --target .tools yt-dlp imageio-ffmpeg
Run: python download_videos.py
"""
import concurrent.futures
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / '.tools'))
import yt_dlp
import imageio_ffmpeg


def main():
    data = json.loads((ROOT / 'data.js').read_text(encoding='utf-8')[18:-2])
    folder = ROOT / 'media' / 'videos'
    folder.mkdir(parents=True, exist_ok=True)
    ffmpeg = ROOT / '.tools' / 'ffmpeg.exe'
    if not ffmpeg.exists():
        shutil.copyfile(imageio_ffmpeg.get_ffmpeg_exe(), ffmpeg)
    records = {}
    manifest = ROOT / 'local_media.json'
    if manifest.exists():
        records = json.loads(manifest.read_text(encoding='utf-8')).get('videos', {})

    def download(sign):
        video_id = sign['video'].rstrip('/').split('/')[-1]
        relative = f'media/videos/{sign["code"]}_{video_id}.mp4'
        target = ROOT / relative
        result = {'source': sign['video'], 'entryId': sign['entryId'], 'code': sign['code'], 'path': relative}
        try:
            if not target.exists():
                options = {'outtmpl': str(target), 'format': 'bestvideo[ext=mp4][height<=720]+bestaudio/bestvideo[ext=mp4][height<=720]',
                           'merge_output_format': 'mp4', 'http_headers': {'Referer': 'https://asl-lex.org/'},
                           'ffmpeg_location': str(ffmpeg), 'quiet': True, 'no_warnings': True,
                           'noprogress': True, 'retries': 3, 'fragment_retries': 3, 'socket_timeout': 30,
                           'overwrites': False, 'concurrent_fragment_downloads': 2}
                with yt_dlp.YoutubeDL(options) as downloader:
                    info = downloader.extract_info(sign['video'], download=True)
                    if str(info['id']) != video_id:
                        raise ValueError('Downloaded video ID differs from official mapping')
                    result.update(title=info.get('title'), duration=info.get('duration'),
                                  width=info.get('width'), height=info.get('height'), format=info.get('format_id'))
            else:
                result = {**records.get(sign['id'], {}), **result}
            # Decode the entire video, including its final frames, not just its header.
            check = subprocess.run([str(ffmpeg), '-v', 'error', '-xerror', '-i', str(target),
                                    '-map', '0:v:0', '-f', 'null', '-'], capture_output=True, timeout=90)
            if check.returncode:
                raise ValueError(check.stderr.decode(errors='replace')[:500])
            result.update(status='verified', bytes=target.stat().st_size,
                          sha256=hashlib.sha256(target.read_bytes()).hexdigest())
            print(f'{sign["rank"]:3} OK {sign["entryId"]} ({result["bytes"]} bytes)', flush=True)
        except Exception as error:
            result.update(status='failed', error=str(error)[:600])
            print(f'{sign["rank"]:3} FAILED {sign["entryId"]}: {error}', flush=True)
        return sign['id'], result

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        for future in concurrent.futures.as_completed([executor.submit(download, sign) for sign in data['signs']]):
            identity, result = future.result()
            records[identity] = result
            manifest.write_text(json.dumps({'checkedAtUTC': datetime.now(timezone.utc).isoformat(),
                                           'verification': 'Every verified file fully decoded with FFmpeg.',
                                           'videos': records}, indent=2) + '\n', encoding='utf-8')
    # Regenerate metadata using verified local media while preserving hosted source references.
    subprocess.run([sys.executable, str(ROOT / 'prepare_data.py')], check=True)
    failed = [s['id'] for s in data['signs'] if records[s['id']]['status'] != 'verified']
    print(f'Verified {len(data["signs"]) - len(failed)}/{len(data["signs"])} local videos. Failed: {failed}')
    if failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
