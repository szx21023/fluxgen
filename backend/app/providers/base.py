from abc import ABC, abstractmethod
from dataclasses import dataclass


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
    async def image_to_video(
        self, image_path: str, prompt: str | None, duration: int
    ) -> GenerationResult:
        """圖片(+可選文字) → 影片。duration 為影片秒數。"""
        raise NotImplementedError
