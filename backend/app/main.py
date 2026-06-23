import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import jobs
from app.config import BASE_DIR, UPLOAD_DIR, settings
from app.schemas import CreateTextJobRequest, JobKind, JobResponse

app = FastAPI(title="AI 影片生成 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 把 outputs/ 與 uploads/ 以靜態檔案方式公開，前端可直接播放
app.mount("/files", StaticFiles(directory=BASE_DIR), name="files")

_ALLOWED_IMAGE = {"image/png", "image/jpeg", "image/webp"}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "provider": settings.video_provider}


@app.post("/api/jobs/text", response_model=JobResponse)
def create_text_job(req: CreateTextJobRequest, bg: BackgroundTasks) -> JobResponse:
    """文生影片：提交文字，立刻回 job_id，影片在背景生成。"""
    if not req.prompt.strip():
        raise HTTPException(400, "prompt 不可為空")
    job = jobs.create_job(JobKind.text_to_video, prompt=req.prompt.strip(), image_path=None)
    bg.add_task(jobs.run_job, job.id)
    return JobResponse.from_job(job)


@app.post("/api/jobs/image", response_model=JobResponse)
async def create_image_job(
    bg: BackgroundTasks,
    image: UploadFile = File(...),
    prompt: str | None = Form(None),
) -> JobResponse:
    """圖生影片：上傳圖片(+可選文字)，立刻回 job_id。"""
    if image.content_type not in _ALLOWED_IMAGE:
        raise HTTPException(400, f"不支援的圖片格式: {image.content_type}")

    ext = Path(image.filename or "").suffix or ".png"
    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    dest.write_bytes(await image.read())

    job = jobs.create_job(
        JobKind.image_to_video,
        prompt=(prompt or "").strip() or None,
        image_path=str(dest),
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
