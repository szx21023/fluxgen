import asyncio
import os
import shutil
import tempfile
from pathlib import Path

from app.providers.base import GenerationResult, ProviderError, VideoProvider

_FFMPEG = shutil.which("ffmpeg")


def _escape_drawtext(text: str) -> str:
    """drawtext 的特殊字元跳脫。"""
    text = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "")
    return text[:60]  # 避免太長塞爆畫面


class MockProvider(VideoProvider):
    """假的影片生成器：不呼叫任何外部 API，用 ffmpeg 產生一段
    帶有 prompt 文字的測試影片，純粹把整條流程跑通。

    需要系統有 ffmpeg；缺少時直接 raise，讓任務正確標為 failed，
    而非回一個壞掉的 placeholder mp4 卻被當成功。
    """

    name = "mock"

    async def _render(self, label: str, duration: int) -> GenerationResult:
        # 模擬真實 API 需要等待的感覺
        await asyncio.sleep(2)

        if not _FFMPEG:
            raise ProviderError(
                "mock provider 需要 ffmpeg，但系統找不到 ffmpeg 執行檔。請安裝 ffmpeg，或改用其他 video_provider。"
            )

        # mkstemp 原子建檔（避免 mktemp 的 TOCTOU）；fd 用不到，關掉避免洩漏，ffmpeg 以 -y 直接覆寫這個空檔。
        fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)
        out = Path(tmp_path)
        try:
            drawtext = (
                f"drawtext=text='{_escape_drawtext(label)}':"
                "fontcolor=white:fontsize=36:x=(w-text_w)/2:y=(h-text_h)/2:"
                "box=1:boxcolor=black@0.5:boxborderw=12"
            )
            cmd = [
                _FFMPEG,
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"testsrc=size=1280x720:rate=24:duration={duration}",
                "-vf",
                drawtext,
                "-pix_fmt",
                "yuv420p",
                "-t",
                str(duration),
                str(out),
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"ffmpeg 失敗: {stderr.decode()[-500:]}")

            data = out.read_bytes()
            return GenerationResult(video_bytes=data)
        finally:
            try:
                out.unlink(missing_ok=True)
            except OSError:
                pass  # 清理失敗絕不可蓋掉真正的 render 錯誤

    async def text_to_video(self, prompt: str, duration: int) -> GenerationResult:
        return await self._render(f"[MOCK] {prompt} ({duration}s)", duration)

    async def image_to_video(self, image_path: str, prompt: str | None, duration: int) -> GenerationResult:
        return await self._render(f"[MOCK img] {prompt or 'image'} ({duration}s)", duration)
