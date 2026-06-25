import logging
import time
import uuid

from app.config import OUTPUT_DIR
from app.providers import get_provider
from app.providers.base import GenerationResult, ProviderError
from app.schemas import Job, JobKind, JobStatus

logger = logging.getLogger(__name__)

# 簡單的記憶體任務表。正式上線可換成 Redis / DB，介面不變。
_jobs: dict[str, Job] = {}


def _now() -> float:
    return time.time()


def create_job(kind: JobKind, prompt: str | None, image_path: str | None, duration: int) -> Job:
    job_id = uuid.uuid4().hex
    job = Job(
        id=job_id,
        kind=kind,
        status=JobStatus.pending,
        prompt=prompt,
        image_path=image_path,
        duration=duration,
        provider=get_provider().name,
        created_at=_now(),
        updated_at=_now(),
    )
    _jobs[job_id] = job
    return job


def get_job(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def _set_status(job: Job, status: JobStatus, **fields) -> None:
    job.status = status
    job.updated_at = _now()
    for k, v in fields.items():
        setattr(job, k, v)


async def run_job(job_id: str) -> None:
    """背景執行：呼叫 Provider 生成影片，存檔，更新狀態。

    FastAPI 的 BackgroundTasks 會在回應送出後執行這個函式。
    """
    job = _jobs.get(job_id)
    if job is None:
        return

    provider = get_provider()
    _set_status(job, JobStatus.running)
    try:
        if job.kind is JobKind.text_to_video:
            result: GenerationResult = await provider.text_to_video(job.prompt or "", job.duration)
        else:
            result = await provider.image_to_video(job.image_path or "", job.prompt, job.duration)

        out_path = OUTPUT_DIR / f"{job_id}.{result.ext}"
        out_path.write_bytes(result.video_bytes)
        _set_status(job, JobStatus.done, video_url=f"/files/outputs/{out_path.name}")
    except ProviderError as exc:
        # 已整理過、可直接給使用者看的失敗原因；後端留一筆紀錄即可，不需完整堆疊。
        logger.warning("job %s failed: %s", job_id, exc)
        _set_status(job, JobStatus.failed, error=str(exc))
    except Exception:  # noqa: BLE001 — 任何失敗都要記在任務上，但細節不外洩
        # 非預期例外（如 FileNotFoundError 會夾帶 uploads/ 絕對路徑）：完整堆疊只進後端 log，
        # 前端只收到一則通用訊息，避免洩漏伺服器路徑/內部結構。
        logger.exception("job %s crashed unexpectedly", job_id)
        _set_status(job, JobStatus.failed, error="影片生成失敗，請稍後再試。")
