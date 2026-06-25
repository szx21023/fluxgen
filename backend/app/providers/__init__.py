from app.config import settings
from app.providers.base import MediaProvider
from app.providers.fal import FalProvider
from app.providers.mock import MockProvider


def get_provider() -> MediaProvider:
    """依設定挑選影片 Provider。換模型只改這裡 / .env。"""
    name = settings.video_provider.lower()
    if name == "fal":
        return FalProvider()
    if name == "mock":
        return MockProvider()
    raise ValueError(f"未知的 VIDEO_PROVIDER: {settings.video_provider!r}")
