from enum import Enum
from typing import Literal, get_args

from pydantic import BaseModel

# 影片時長（秒）。目前 Kling 模型只收 5 / 10；換支援其他時長的模型時只改這個
# Literal。VideoDuration 是唯一來源：用於 JSON 請求（pydantic 直接把 JSON 數字
# 對上 Literal），ALLOWED_DURATIONS 則由它推導，給 form 端點手動檢查用（見
# main.py）——因為 multipart 欄位是字串、無法直接對上 int 的 Literal。
VideoDuration = Literal[5, 10]
ALLOWED_DURATIONS = get_args(VideoDuration)
DEFAULT_DURATION = 5


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class JobKind(str, Enum):
    text_to_video = "text_to_video"
    image_to_video = "image_to_video"
    text_to_image = "text_to_image"
    image_to_image = "image_to_image"


class Job(BaseModel):
    id: str
    kind: JobKind
    status: JobStatus = JobStatus.pending
    prompt: str | None = None
    image_path: str | None = None
    duration: VideoDuration = DEFAULT_DURATION
    # 完成後可供前端下載/播放的相對 URL
    video_url: str | None = None
    error: str | None = None
    provider: str
    created_at: float
    updated_at: float


class CreateTextJobRequest(BaseModel):
    prompt: str
    duration: VideoDuration = DEFAULT_DURATION


class CreateTextImageJobRequest(BaseModel):
    """文字生圖：只需 prompt，生圖無 duration 概念。"""

    prompt: str


class JobResponse(BaseModel):
    """回給前端的精簡版（不外洩內部檔案路徑）。"""

    id: str
    kind: JobKind
    status: JobStatus
    prompt: str | None = None
    duration: VideoDuration = DEFAULT_DURATION
    video_url: str | None = None
    error: str | None = None
    provider: str

    @classmethod
    def from_job(cls, job: Job) -> "JobResponse":
        return cls(
            id=job.id,
            kind=job.kind,
            status=job.status,
            prompt=job.prompt,
            duration=job.duration,
            video_url=job.video_url,
            error=job.error,
            provider=job.provider,
        )
