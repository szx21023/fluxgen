import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app import jobs
from app.config import OUTPUT_DIR, UPLOAD_DIR, settings
from app.schemas import (
    ALLOWED_DURATIONS,
    DEFAULT_DURATION,
    CreateTextJobRequest,
    JobKind,
    JobResponse,
)

app = FastAPI(title="AI 影片生成 API", version="0.1.0")

_ALLOWED_IMAGE = {"image/png", "image/jpeg", "image/webp"}
_UPLOAD_CHUNK = 1024 * 1024  # 1 MiB 一塊串流寫入，避免整檔進記憶體
# Content-Length 早期攔截給一點寬限：multipart 邊界/標頭/prompt 欄位讓 body 略大於純檔案
# 位元組，故這層只擋「明顯過大」，精確上限交給 handler 的串流累計（縱深防禦的第二層）。
_UPLOAD_BODY_SLACK = _UPLOAD_CHUNK


async def reject_oversized_upload(request: Request, call_next):
    """在 multipart 解析前，先用 Content-Length 擋掉明顯過大的上傳。

    FastAPI 會在 handler 執行「之前」就把整包 body 解析進系統暫存檔，
    所以 handler 內的大小檢查發生得太晚，擋不住磁碟被暫存檔塞爆。
    這裡趁早攔截一般 client（瀏覽器上傳 multipart 一定帶 Content-Length）。
    不帶、或無法解析 Content-Length 的 chunked 上傳，仍會落到 handler 的串流檢查。
    """
    if request.method == "POST" and request.url.path == "/api/jobs/image":
        content_length = request.headers.get("content-length")
        try:
            declared = int(content_length) if content_length else None
        except ValueError:
            declared = None  # 標頭無法解析 → 當作未知長度，交給 handler 串流檢查
        limit = settings.max_upload_mb * 1024 * 1024 + _UPLOAD_BODY_SLACK
        if declared is not None and declared > limit:
            return JSONResponse(
                {"detail": f"圖片過大，上限為 {settings.max_upload_mb} MB"},
                status_code=413,
            )
    return await call_next(request)


# 中介層註冊順序：最後加入者包在最外層。先掛大小攔截、再掛 CORS，讓 CORS 在最外層——
# 這樣連大小攔截回的 413 也會帶上 CORS 標頭，跨網域前端才看得到 413 而非 opaque CORS 錯誤。
app.add_middleware(BaseHTTPMiddleware, dispatch=reject_oversized_upload)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 只把 outputs/ 以靜態檔案方式公開，前端可直接播放。
# 注意：絕不要掛 BASE_DIR——那會把 .env（含 FAL_KEY）與全部原始碼一起對外公開。
app.mount("/files/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "provider": settings.video_provider}


@app.post("/api/jobs/text", response_model=JobResponse)
def create_text_job(req: CreateTextJobRequest, bg: BackgroundTasks) -> JobResponse:
    """文生影片：提交文字，立刻回 job_id，影片在背景生成。"""
    if not req.prompt.strip():
        raise HTTPException(400, "prompt 不可為空")
    job = jobs.create_job(
        JobKind.text_to_video,
        prompt=req.prompt.strip(),
        image_path=None,
        duration=req.duration,
    )
    bg.add_task(jobs.run_job, job.id)
    return JobResponse.from_job(job)


@app.post("/api/jobs/image", response_model=JobResponse)
async def create_image_job(
    bg: BackgroundTasks,
    image: UploadFile = File(...),
    prompt: str | None = Form(None),
    # multipart 欄位是字串，int 會把 "5" 轉成 5；允許值由下方手動檢查（不能用
    # Literal[int]，那對字串表單值會驗不過）。
    duration: int = Form(DEFAULT_DURATION),
) -> JobResponse:
    """圖生影片：上傳圖片(+可選文字)，立刻回 job_id。"""
    if image.content_type not in _ALLOWED_IMAGE:
        raise HTTPException(400, f"不支援的圖片格式: {image.content_type}")
    if duration not in ALLOWED_DURATIONS:
        allowed = " / ".join(str(d) for d in ALLOWED_DURATIONS)
        raise HTTPException(422, f"duration 只接受 {allowed} 秒")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    ext = Path(image.filename or "").suffix or ".png"
    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"

    # 串流分塊寫入並累計大小：超過上限就中止、清掉半成品、回 413。
    total = 0
    try:
        with dest.open("wb") as out:
            while chunk := await image.read(_UPLOAD_CHUNK):
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        413, f"圖片過大，上限為 {settings.max_upload_mb} MB"
                    )
                out.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise

    job = jobs.create_job(
        JobKind.image_to_video,
        prompt=(prompt or "").strip() or None,
        image_path=str(dest),
        duration=duration,
    )
    bg.add_task(jobs.run_job, job.id)
    return JobResponse.from_job(job)


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> JobResponse:
    """前端輪詢這個端點查任務狀態。"""
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(404, "找不到此任務")
    return JobResponse.from_job(job)
