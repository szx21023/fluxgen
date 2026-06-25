from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 專案根目錄底下的存放區
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    video_provider: str = "mock"

    # 上傳圖片大小上限（MB）；超過回 413。必須 > 0，否則所有上傳都會被擋。
    max_upload_mb: int = Field(10, gt=0)

    fal_key: str = ""
    fal_text_model: str = "fal-ai/kling-video/v2/standard/text-to-video"
    fal_image_model: str = "fal-ai/kling-video/v2/standard/image-to-video"
    # 生圖模型；回應格式同為 {"images":[{"url"...}]}。換模型只改 .env。
    # 文生圖：FLUX.1 [dev]。圖生圖：FLUX.1 Kontext（指令式編輯，prompt 為編輯指令、保留人物，不吃 strength）。
    fal_text_image_model: str = "fal-ai/flux/dev"
    fal_image_image_model: str = "fal-ai/flux-pro/kontext"

    # 逗號分隔的允許來源
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

# 確保存放目錄存在
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
