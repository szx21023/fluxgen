import asyncio
import base64
import json
from collections.abc import Callable
from pathlib import Path

import httpx

from app.config import settings
from app.providers.base import GenerationResult, MediaProvider, ProviderError

# fal.ai 佇列式 API：提交後拿到 status_url / response_url，輪詢到完成
_QUEUE_BASE = "https://queue.fal.run"
_POLL_INTERVAL = 3.0
_MAX_WAIT = 600  # 秒；文生影片有時要好幾分鐘

# 由副檔名推 data URI 的 mime。副檔名在上傳時已由 magic bytes 偵測決定（見
# main._sniff_image_type），故這裡是權威來源；用明確對照表而非 mimetypes，
# 避免依賴 OS 的 /etc/mime.types（精簡環境可能認不得 .webp 而誤判成 png）。
_EXT_TO_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}

_DETAIL_MAX = 300


def _clip(text: str) -> str:
    """截斷過長訊息；被截斷時加註，避免誤把片段當成完整原文。"""
    return text if len(text) <= _DETAIL_MAX else text[:_DETAIL_MAX] + "…(truncated)"


def _fal_detail(resp: httpx.Response) -> str:
    """從 fal 回應裡撈出人看得懂的錯誤訊息。

    fal 把真正的原因放在 body 的 `detail`（例如「餘額用盡」「Path not found」），
    httpx 的 raise_for_status() 只會給一般化的狀態碼字串，所以這裡優先取 detail。
    """
    try:
        body = resp.json()
    except (ValueError, json.JSONDecodeError):
        # 非 JSON body（含空 body / 壞編碼 → UnicodeDecodeError 亦為 ValueError 子類）
        text = resp.text.strip()
        return _clip(text) if text else f"HTTP {resp.status_code}"
    if isinstance(body, dict) and body.get("detail"):
        return str(body["detail"])
    return f"HTTP {resp.status_code}: {_clip(str(body))}"


def _raise_for_status(resp: httpx.Response, action: str) -> None:
    """像 raise_for_status，但把 fal 的 detail 一起帶出來方便除錯。"""
    if resp.is_error:
        raise ProviderError(f"fal.ai {action} 失敗（{resp.status_code}）：{_fal_detail(resp)}")


# 從 COMPLETED 結果取出媒體 URL。佇列可能「假裝收下」無效 model 路徑，最後才在
# 結果裡回 detail，故這裡取不到 URL 就把 fal 的訊息帶出。回 (url, 副檔名, content_type)。
def _extract_video(result: dict) -> tuple[str, str, str]:
    url = (result.get("video") or {}).get("url") if isinstance(result, dict) else None
    if not url:
        detail = result.get("detail") if isinstance(result, dict) else None
        raise ProviderError(
            f"fal.ai 回應沒有影片 URL（可能是 model 路徑無效或回傳格式改變）：{detail or _clip(str(result))}"
        )
    return url, "mp4", "video/mp4"


_IMAGE_CTYPE_TO_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def _extract_image(result: dict) -> tuple[str, str, str]:
    # 安全檢查器命中時 fal 會回一張全黑圖並標記 has_nsfw_concepts；別把黑圖當成功，
    # 直接報明確錯誤（否則前端只會看到「完成」+ 一張全黑圖）。
    if isinstance(result, dict) and any(result.get("has_nsfw_concepts") or []):
        raise ProviderError("圖片被安全機制判定為不當內容而擋下（可能誤判）；請換一張圖或調整描述後再試。")
    images = result.get("images") if isinstance(result, dict) else None
    first = images[0] if isinstance(images, list) and images else None
    url = first.get("url") if isinstance(first, dict) else None
    if not url:
        detail = result.get("detail") if isinstance(result, dict) else None
        raise ProviderError(
            f"fal.ai 回應沒有圖片 URL（可能是 model 路徑無效或回傳格式改變）：{detail or _clip(str(result))}"
        )
    ctype = first.get("content_type") or "image/jpeg"
    return url, _IMAGE_CTYPE_TO_EXT.get(ctype, "jpg"), ctype


class FalProvider(MediaProvider):
    """透過 fal.ai 聚合層呼叫媒體模型（影片 Kling、圖片 FLUX 等）。

    fal.ai 的好處：一把 FAL_KEY 就能切換多種模型，只要改 .env 裡的
    FAL_TEXT_MODEL / FAL_IMAGE_MODEL / FAL_TEXT_IMAGE_MODEL / FAL_IMAGE_IMAGE_MODEL。
    所以「換模型」不必動程式碼。
    """

    name = "fal"

    def __init__(self) -> None:
        if not settings.fal_key:
            raise RuntimeError("VIDEO_PROVIDER=fal 但沒有設定 FAL_KEY。請到 https://fal.ai 申請後填進 .env。")
        self._headers = {"Authorization": f"Key {settings.fal_key}"}

    async def _submit_and_wait(
        self, model: str, payload: dict, extract: Callable[[dict], tuple[str, str, str]]
    ) -> GenerationResult:
        """提交任務 → 輪詢到完成 → 用 extract 取媒體 URL → 下載並回傳。

        extract 依模型回傳格式（影片 `video.url` / 圖片 `images[].url`）抽出
        (url, 副檔名, content_type)，所以影片與圖片共用同一條佇列流程。
        """
        async with httpx.AsyncClient(timeout=60) as client:
            # 1) 提交任務到佇列
            submit = await client.post(f"{_QUEUE_BASE}/{model}", headers=self._headers, json=payload)
            _raise_for_status(submit, "提交任務")
            queued = submit.json()
            status_url = queued.get("status_url")
            response_url = queued.get("response_url")
            if not status_url or not response_url:
                raise ProviderError(f"fal.ai 提交回應缺少 status_url/response_url：{_clip(str(queued))}")

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
                    raise ProviderError(f"fal.ai 任務 {status}：{detail}")
            else:
                raise ProviderError(f"fal.ai 任務超時（超過 {_MAX_WAIT} 秒）")

            # 3) 取結果，下載媒體
            done = await client.get(response_url, headers=self._headers)
            _raise_for_status(done, "取得任務結果")
            url, ext, ctype = extract(done.json())
            media = await client.get(url)
            _raise_for_status(media, "下載結果")
            return GenerationResult(media_bytes=media.content, content_type=ctype, ext=ext)

    @staticmethod
    def _image_data_uri(image_path: str) -> str:
        """讀上傳圖檔轉成 fal 接受的 data URI（免另外上傳圖床）。

        檔案遺失時給明確訊息且不外洩伺服器絕對路徑。
        """
        path = Path(image_path)
        mime = _EXT_TO_MIME.get(path.suffix.lower(), "image/png")
        try:
            raw = path.read_bytes()
        except FileNotFoundError as exc:
            raise ProviderError("找不到上傳的圖片檔，可能已被清除，請重新上傳。") from exc
        return f"data:{mime};base64,{base64.b64encode(raw).decode()}"

    async def text_to_video(self, prompt: str, duration: int) -> GenerationResult:
        # Kling 的 duration 是字串列舉（"5" / "10"）
        payload = {"prompt": prompt, "duration": str(duration)}
        return await self._submit_and_wait(settings.fal_text_model, payload, _extract_video)

    async def image_to_video(self, image_path: str, prompt: str | None, duration: int) -> GenerationResult:
        payload: dict = {"image_url": self._image_data_uri(image_path), "duration": str(duration)}
        if prompt:
            payload["prompt"] = prompt
        return await self._submit_and_wait(settings.fal_image_model, payload, _extract_video)

    async def text_to_image(self, prompt: str, guidance_scale: float) -> GenerationResult:
        # 關閉安全檢查器：自用工具，避免人物等正常內容被誤判塗黑（FLUX dev 支援此旗標）。
        payload = {"prompt": prompt, "guidance_scale": guidance_scale, "enable_safety_checker": False}
        return await self._submit_and_wait(settings.fal_text_image_model, payload, _extract_image)

    async def image_to_image(self, image_path: str, prompt: str, guidance_scale: float) -> GenerationResult:
        # FLUX Kontext：指令式編輯（prompt 為編輯指令、保留人物），不吃 strength。
        # guidance_scale 越高越照指令；safety_tolerance 放寬到 5（1~6，越高越寬鬆）減少誤擋。
        payload = {
            "image_url": self._image_data_uri(image_path),
            "prompt": prompt,
            "guidance_scale": guidance_scale,
            "safety_tolerance": "5",
        }
        return await self._submit_and_wait(settings.fal_image_image_model, payload, _extract_image)
