from __future__ import annotations
import logging, os, tempfile, time, uuid
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI
from pydantic import BaseModel, Field
logging.basicConfig(level=logging.INFO)
logger=logging.getLogger(__name__)
app=FastAPI(title='social-worker',version='1.0.0')
class DownloadRequest(BaseModel):
    url:str=Field(min_length=1)
    facebook_cookie:str|None=None
class DownloadResponse(BaseModel):
    success:bool
    media_path:str|None=None
    info:dict|None=None
    elapsed_seconds:float|None=None
    error:str|None=None
    stage:str|None=None

@app.get('/health')
def health()->dict:
    return {"status":"ok","service":"social-worker"}

def _attempt_download(source_url:str,options:dict)->tuple[dict,str]:
    import yt_dlp
    with yt_dlp.YoutubeDL(options) as ydl:
        info=ydl.extract_info(source_url,download=False) or {}
        downloaded_info=ydl.extract_info(source_url,download=True) or info
        return info, ydl.prepare_filename(downloaded_info)

@app.post('/download/social-video',response_model=DownloadResponse)
def download_social_video(payload:DownloadRequest)->DownloadResponse:
    started_at=time.monotonic(); source_url=payload.url.strip(); cookie=(payload.facebook_cookie or '').strip() or None
    logger.info('social_downloader_request_started source_host=%s cookie_provided=%s',urlparse(source_url).netloc or 'unknown',bool(cookie))
    download_root=Path(os.getenv('SOCIAL_DOWNLOADER_OUTPUT_DIR','/app/data/social-downloads')); download_root.mkdir(parents=True,exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(dir=str(download_root)) as tmp_dir:
            out=str(Path(tmp_dir)/'media.%(ext)s'); base={"quiet":False,"no_warnings":False,"noprogress":True,"noplaylist":True,"format":'bestaudio/best',"outtmpl":out}
            cookie_file=None
            if cookie:
                cookie_file=str(Path(tmp_dir)/'facebook-cookie.txt'); Path(cookie_file).write_text(cookie,encoding='utf-8')
            attempts=[dict(base, cookiefile=cookie_file),dict(base)] if cookie_file else [dict(base)]
            last_exc=None
            for options in attempts:
                try:
                    info,downloaded_path=_attempt_download(source_url,options); break
                except Exception as exc:
                    last_exc=exc
            else:
                raise last_exc or RuntimeError('yt_dlp_extract_failed')
            shared_path=download_root/f"{uuid.uuid4()}-{Path(downloaded_path).name}"
            Path(downloaded_path).replace(shared_path)
            elapsed=round(time.monotonic()-started_at,3)
            logger.info('social_downloader_ytdlp_success media_path=%s elapsed_s=%.3f',str(shared_path),elapsed)
            return DownloadResponse(success=True,media_path=str(shared_path),info=info,elapsed_seconds=elapsed)
    except Exception as exc:
        elapsed=round(time.monotonic()-started_at,3)
        logger.warning('social_downloader_ytdlp_failure elapsed_s=%.3f',elapsed)
        return DownloadResponse(success=False,error=str(exc) or 'download_failed',stage='yt-dlp')
