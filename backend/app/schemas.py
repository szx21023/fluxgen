from enum import Enum

from pydantic import BaseModel


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class JobKind(str, Enum):
    text_to_video = "text_to_video"
    image_to_video = "image_to_video"


class Job(BaseModel):
    id: str
    kind: JobKind
    status: JobStatus = JobStatus.pending
    prompt: str | None = None
    image_path: str | None = None
    # 完成後可供前端下載/播放的相對 URL
    video_url: str | None = None
    error: str | None = None
    provider: str
    created_at: float
    updated_at: float


class CreateTextJobRequest(BaseModel):
    prompt: str


class JobResponse(BaseModel):
    """回給前端的精簡版（不外洩內部檔案路徑）。"""

    id: str
    kind: JobKind
    status: JobStatus
    prompt: str | None = None
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
            video_url=job.video_url,
            error=job.error,
            provider=job.provider,
        )
