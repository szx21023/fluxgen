import asyncio
import base64
import mimetypes
from pathlib import Path

import httpx

from app.config import settings
from app.providers.base import GenerationResult, VideoProvider

# fal.ai 佇列式 API：提交後拿到 status_url / response_url，輪詢到完成
_QUEUE_BASE = "https://queue.fal.run"
_POLL_INTERVAL = 3.0
_MAX_WAIT = 600  # 秒；文生影片有時要好幾分鐘


def _fal_detail(resp: httpx.Response) -> str:
    """從 fal 回應裡撈出人看得懂的錯誤訊息。

    fal 把真正的原因放在 body 的 `detail`（例如「餘額用盡」「Path not found」），
    httpx 的 raise_for_status() 只會給一般化的狀態碼字串，所以這裡優先取 detail。
    """
    try:
        body = resp.json()
    except Exception:
        text = resp.text.strip()
        return text[:300] if text else f"HTTP {resp.status_code}"
    if isinstance(body, dict) and body.get("detail"):
        return str(body["detail"])
    return f"HTTP {resp.status_code}: {str(body)[:300]}"


def _raise_for_status(resp: httpx.Response, action: str) -> None:
    """像 raise_for_status，但把 fal 的 detail 一起帶出來方便除錯。"""
    if resp.is_error:
        raise RuntimeError(f"fal.ai {action} 失敗（{resp.status_code}）：{_fal_detail(resp)}")


class FalProvider(VideoProvider):
    """透過 fal.ai 聚合層呼叫影片模型（Kling / Sora / Veo 等）。

    fal.ai 的好處：一把 FAL_KEY 就能切換多種模型，只要改 .env 裡的
    FAL_TEXT_MODEL / FAL_IMAGE_MODEL。所以「換模型」不必動程式碼。
    """

    name = "fal"

    def __init__(self) -> None:
        if not settings.fal_key:
            raise RuntimeError(
                "VIDEO_PROVIDER=fal 但沒有設定 FAL_KEY。"
                "請到 https://fal.ai 申請後填進 .env。"
            )
        self._headers = {"Authorization": f"Key {settings.fal_key}"}

    async def _submit_and_wait(self, model: str, payload: dict) -> GenerationResult:
        async with httpx.AsyncClient(timeout=60) as client:
            # 1) 提交任務到佇列
            submit = await client.post(
                f"{_QUEUE_BASE}/{model}", headers=self._headers, json=payload
            )
            _raise_for_status(submit, "提交任務")
            queued = submit.json()
            status_url = queued.get("status_url")
            response_url = queued.get("response_url")
            if not status_url or not response_url:
                raise RuntimeError(
                    f"fal.ai 提交回應缺少 status_url/response_url：{str(queued)[:300]}"
                )

            # 2) 輪詢直到完成
            waited = 0.0
            while waited < _MAX_WAIT:
                await asyncio.sleep(_POLL_INTERVAL)
                waited += _POLL_INTERVAL
                st = await client.get(status_url, headers=self._headers)
                _raise_for_status(st, "查詢任務狀態")
                status = st.json().get("status")
                if status == "COMPLETED":
                    break
                if status in ("FAILED", "CANCELLED"):
                    # 失敗時 response_url 通常帶有 fal 的詳細原因
                    detail = _fal_detail(await client.get(response_url, headers=self._headers))
                    raise RuntimeError(f"fal.ai 任務 {status}：{detail}")
            else:
                raise TimeoutError(f"fal.ai 任務超時（超過 {_MAX_WAIT} 秒）")

            # 3) 取結果，下載影片
            done = await client.get(response_url, headers=self._headers)
            _raise_for_status(done, "取得任務結果")
            result = done.json()
            # 佇列可能「假裝收下」無效的 model 路徑，最後在結果裡才回 detail 報錯，
            # 因此 COMPLETED 也要確認真的有影片 URL，否則把 fal 的訊息原封帶出。
            video_url = (result.get("video") or {}).get("url") if isinstance(result, dict) else None
            if not video_url:
                detail = result.get("detail") if isinstance(result, dict) else None
                raise RuntimeError(
                    "fal.ai 回應沒有影片 URL（可能是 model 路徑無效或回傳格式改變）："
                    f"{detail or str(result)[:300]}"
                )
            video = await client.get(video_url)
            _raise_for_status(video, "下載影片")
            return GenerationResult(video_bytes=video.content)

    async def text_to_video(self, prompt: str) -> GenerationResult:
        return await self._submit_and_wait(
            settings.fal_text_model, {"prompt": prompt}
        )

    async def image_to_video(self, image_path: str, prompt: str | None) -> GenerationResult:
        # fal.ai 接受 data URI 當作圖片輸入，免去另外上傳圖床
        path = Path(image_path)
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        b64 = base64.b64encode(path.read_bytes()).decode()
        payload: dict = {"image_url": f"data:{mime};base64,{b64}"}
        if prompt:
            payload["prompt"] = prompt
        return await self._submit_and_wait(settings.fal_image_model, payload)
