import { useEffect, useRef, useState } from "react";
import { pollJob, submitImageJob, submitTextJob } from "./api";

const STATUS_LABEL = {
  pending: "排隊中…",
  running: "AI 生成中…",
  done: "完成",
  failed: "失敗",
};

export default function App() {
  const [mode, setMode] = useState("text"); // "text" | "image"
  const [prompt, setPrompt] = useState("");
  const [file, setFile] = useState(null);
  const [job, setJob] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const stopPoll = useRef(null);

  // 卸載時停止輪詢
  useEffect(() => () => stopPoll.current?.(), []);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setJob(null);
    stopPoll.current?.();

    try {
      setBusy(true);
      const created =
        mode === "text"
          ? await submitTextJob(prompt)
          : await submitImageJob(file, prompt);
      setJob(created);
      stopPoll.current = pollJob(created.id, setJob);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const inProgress =
    job && (job.status === "pending" || job.status === "running");
  const canSubmit =
    !busy && !inProgress && (mode === "text" ? prompt.trim() : file);

  return (
    <div className="app">
      <h1>AI 影片生成</h1>
      <p className="sub">上傳圖片或輸入文字，交給 AI 生成影片</p>

      <div className="tabs">
        <button
          className={mode === "text" ? "active" : ""}
          onClick={() => setMode("text")}
        >
          文字 → 影片
        </button>
        <button
          className={mode === "image" ? "active" : ""}
          onClick={() => setMode("image")}
        >
          圖片 → 影片
        </button>
      </div>

      <form onSubmit={handleSubmit} className="card">
        {mode === "image" && (
          <label className="field">
            <span>圖片</span>
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
        )}

        <label className="field">
          <span>
            {mode === "text" ? "描述你想要的影片" : "補充描述（可選）"}
          </span>
          <textarea
            rows={3}
            value={prompt}
            placeholder={
              mode === "text"
                ? "例：夕陽下海浪拍打沙灘，鏡頭緩緩推進"
                : "例：讓畫面中的人物微笑並轉頭"
            }
            onChange={(e) => setPrompt(e.target.value)}
          />
        </label>

        <button type="submit" disabled={!canSubmit}>
          {inProgress ? "生成中…" : "開始生成"}
        </button>
      </form>

      {error && <div className="error">⚠️ {error}</div>}

      {job && (
        <div className="card result">
          <div className="status">
            <span className={`dot ${job.status}`} />
            {STATUS_LABEL[job.status] ?? job.status}
            <span className="provider">provider: {job.provider}</span>
          </div>

          {job.status === "failed" && (
            <div className="error">{job.error}</div>
          )}

          {job.status === "done" && job.video_url && (
            <video
              key={job.video_url}
              src={job.video_url}
              controls
              autoPlay
              loop
            />
          )}
        </div>
      )}
    </div>
  );
}
