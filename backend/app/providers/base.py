from abc import ABC, abstractmethod
from dataclasses import dataclass


class ProviderError(Exception):
    """Provider 生成失敗，且訊息已經過整理、可安全顯示給前端使用者。

    用這個區分「可直接給使用者看的原因」（餘額用盡、缺 ffmpeg、任務超時…）
    與「非預期的內部例外」（會夾帶伺服器路徑/堆疊）。後者一律在後端記 log，
    只回前端一則通用訊息，避免洩漏內部細節。詳見 jobs.run_job。
    """


@dataclass
class GenerationResult:
    """Provider 產出影片後回傳的結果。

    video_bytes: 影片二進位內容；後端統一存到 outputs/ 再以 URL 回給前端。
    """

    video_bytes: bytes
    content_type: str = "video/mp4"
    ext: str = "mp4"


class VideoProvider(ABC):
    """所有影片生成 Provider 的統一介面。

    新增一家服務 = 寫一個子類別實作這兩個方法，
    再到 providers/__init__.py 的 get_provider() 註冊即可，
    後端流程與前端完全不用改。
    """

    name: str = "base"

    @abstractmethod
    async def text_to_video(self, prompt: str, duration: int) -> GenerationResult:
        """文字 → 影片。duration 為影片秒數。"""
        raise NotImplementedError

    @abstractmethod
    async def image_to_video(self, image_path: str, prompt: str | None, duration: int) -> GenerationResult:
        """圖片(+可選文字) → 影片。duration 為影片秒數。"""
        raise NotImplementedError
