// 與後端溝通的薄封裝層

export async function submitTextJob(prompt) {
  const res = await fetch("/api/jobs/text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  if (!res.ok) throw new Error((await res.json()).detail || "提交失敗");
  return res.json();
}

export async function submitImageJob(file, prompt) {
  const form = new FormData();
  form.append("image", file);
  if (prompt) form.append("prompt", prompt);
  const res = await fetch("/api/jobs/image", { method: "POST", body: form });
  if (!res.ok) throw new Error((await res.json()).detail || "提交失敗");
  return res.json();
}

export async function getJob(jobId) {
  const res = await fetch(`/api/jobs/${jobId}`);
  if (!res.ok) throw new Error("查詢任務失敗");
  return res.json();
}

// 每隔一段時間輪詢任務狀態，直到 done / failed
export function pollJob(jobId, onUpdate, { interval = 2500 } = {}) {
  let stopped = false;
  async function tick() {
    if (stopped) return;
    try {
      const job = await getJob(jobId);
      onUpdate(job);
      if (job.status === "done" || job.status === "failed") return;
    } catch (e) {
      onUpdate({ status: "failed", error: e.message });
      return;
    }
    setTimeout(tick, interval);
  }
  tick();
  return () => {
    stopped = true;
  };
}
