// 與後端溝通的薄封裝層

// 從錯誤回應取出後端的 detail；回應若非 JSON（如 500 HTML 頁）也不讓 res.json()
// 丟錯蓋掉真正的狀態碼。
async function errorMessage(res, fallback) {
  const body = await res.json().catch(() => ({}));
  return body.detail || `${fallback}（${res.status}）`;
}

export async function submitTextJob(prompt, duration) {
  const res = await fetch("/api/jobs/text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, duration }),
  });
  if (!res.ok) throw new Error(await errorMessage(res, "提交失敗"));
  return res.json();
}

export async function submitImageJob(file, prompt, duration) {
  const form = new FormData();
  form.append("image", file);
  if (prompt) form.append("prompt", prompt);
  form.append("duration", duration);
  const res = await fetch("/api/jobs/image", { method: "POST", body: form });
  if (!res.ok) throw new Error(await errorMessage(res, "提交失敗"));
  return res.json();
}

export async function getJob(jobId) {
  const res = await fetch(`/api/jobs/${jobId}`);
  if (!res.ok) throw new Error(await errorMessage(res, "查詢任務失敗"));
  return res.json();
}

// 每隔一段時間輪詢任務狀態，直到 done / failed。
// 韌性：單次查詢失敗（網路抖動、暫時性 5xx）不立即放棄，連續失敗達 maxRetries
// 次才標記失敗；重試間採指數退避（封頂），避免一抖動就讓整個長任務作廢。
export function pollJob(jobId, onUpdate, { interval = 2500, maxRetries = 5 } = {}) {
  let stopped = false;
  let consecutiveErrors = 0;
  async function tick() {
    if (stopped) return;
    try {
      const job = await getJob(jobId);
      consecutiveErrors = 0;
      onUpdate(job);
      if (job.status === "done" || job.status === "failed") return;
      setTimeout(tick, interval);
    } catch (e) {
      consecutiveErrors += 1;
      if (consecutiveErrors >= maxRetries) {
        onUpdate({ status: "failed", error: `連線中斷，已重試 ${maxRetries} 次：${e.message}` });
        return;
      }
      // 指數退避：interval、2×、4×…，封頂 20s。網路恢復後下一次成功即歸零。
      const backoff = Math.min(interval * 2 ** (consecutiveErrors - 1), 20000);
      setTimeout(tick, backoff);
    }
  }
  tick();
  return () => {
    stopped = true;
  };
}
