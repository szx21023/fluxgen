import asyncio
import os
import shutil
import tempfile
from pathlib import Path

from app.providers.base import GenerationResult, MediaProvider, ProviderError

_FFMPEG = shutil.which("ffmpeg")


def _escape_drawtext(text: str) -> str:
    """drawtext 的特殊字元跳脫。"""
    text = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "")
    return text[:60]  # 避免太長塞爆畫面


def _drawtext(label: str) -> str:
    return (
        f"drawtext=text='{_escape_drawtext(label)}':"
        "fontcolor=white:fontsize=36:x=(w-text_w)/2:y=(h-text_h)/2:"
        "box=1:boxcolor=black@0.5:boxborderw=12"
    )


class MockProvider(MediaProvider):
    """假的媒體生成器：不呼叫任何外部 API，用 ffmpeg 產生帶 prompt 文字的測試
    影片/圖片，純粹把整條流程跑通。

    需要系統有 ffmpeg；缺少時直接 raise，讓任務正確標為 failed，
    而非回一個壞掉的 placeholder 卻被當成功。
    """

    name = "mock"

    async def _run_ffmpeg(self, args: list[str], suffix: str, content_type: str, ext: str) -> GenerationResult:
        # 模擬真實 API 需要等待的感覺
        await asyncio.sleep(2)

        if not _FFMPEG:
            raise ProviderError(
                "mock provider 需要 ffmpeg，但系統找不到 ffmpeg 執行檔。請安裝 ffmpeg，或改用其他 video_provider。"
            )

        # mkstemp 原子建檔（避免 mktemp 的 TOCTOU）；fd 用不到，關掉避免洩漏，ffmpeg 以 -y 直接覆寫這個空檔。
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        out = Path(tmp_path)
        try:
            proc = await asyncio.create_subprocess_exec(
                _FFMPEG,
                "-y",
                *args,
                str(out),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"ffmpeg 失敗: {stderr.decode()[-500:]}")
            return GenerationResult(media_bytes=out.read_bytes(), content_type=content_type, ext=ext)
        finally:
            try:
                out.unlink(missing_ok=True)
            except OSError:
                pass  # 清理失敗絕不可蓋掉真正的 render 錯誤

    async def _render_video(self, label: str, duration: int) -> GenerationResult:
        args = [
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size=1280x720:rate=24:duration={duration}",
            "-vf",
            _drawtext(label),
            "-pix_fmt",
            "yuv420p",
            "-t",
            str(duration),
        ]
        return await self._run_ffmpeg(args, ".mp4", "video/mp4", "mp4")

    async def _render_image(self, label: str) -> GenerationResult:
        # 取 testsrc 的單一幀輸出成 PNG
        args = ["-f", "lavfi", "-i", "testsrc=size=1280x720", "-vf", _drawtext(label), "-frames:v", "1"]
        return await self._run_ffmpeg(args, ".png", "image/png", "png")

    async def text_to_video(self, prompt: str, duration: int) -> GenerationResult:
        return await self._render_video(f"[MOCK] {prompt} ({duration}s)", duration)

    async def image_to_video(self, image_path: str, prompt: str | None, duration: int) -> GenerationResult:
        return await self._render_video(f"[MOCK img] {prompt or 'image'} ({duration}s)", duration)

    async def text_to_image(self, prompt: str) -> GenerationResult:
        return await self._render_image(f"[MOCK] {prompt}")

    async def image_to_image(self, image_path: str, prompt: str) -> GenerationResult:
        return await self._render_image(f"[MOCK img2img] {prompt}")
