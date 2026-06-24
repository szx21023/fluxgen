import { useEffect, useRef, useState } from "react";
import { pollJob, submitImageJob, submitTextJob } from "./api";

const STATUS_LABEL = {
  pending: "排隊中…",
  running: "AI 生成中…",
  done: "完成",
  failed: "失敗",
};

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function App() {
  const [mode, setMode] = useState("text"); // "text" | "image"
  const [prompt, setPrompt] = useState("");
  const [duration, setDuration] = useState(5);
  const [file, setFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [job, setJob] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const stopPoll = useRef(null);
  const fileInputRef = useRef(null);

  // 卸載時停止輪詢
  useEffect(() => () => stopPoll.current?.(), []);

  // 依選取的檔案產生本機預覽 URL，換檔/卸載時回收避免記憶體洩漏
  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function clearFile() {
    setFile(null);
    // 清掉 input 的值，否則再次選同一個檔不會觸發 onChange
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function switchMode(next) {
    if (next === mode) return;
    setMode(next);
    // 切換分頁時清掉殘留的圖檔與預覽，避免舊預覽重現、object URL 留著不回收
    clearFile();
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setJob(null);
    stopPoll.current?.();

    try {
      setBusy(true);
      const created =
        mode === "text"
          ? await submitTextJob(prompt, duration)
          : await submitImageJob(file, prompt, duration);
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
          onClick={() => switchMode("text")}
        >
          文字 → 影片
        </button>
        <button
          className={mode === "image" ? "active" : ""}
          onClick={() => switchMode("image")}
        >
          圖片 → 影片
        </button>
      </div>

      <form onSubmit={handleSubmit} className="card">
        {mode === "image" && (
          <label className="field">
            <span>圖片</span>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            {file && previewUrl && (
              <div className="preview">
                <img src={previewUrl} alt="預覽" />
                <div className="preview-meta">
                  <span className="preview-name" title={file.name}>
                    {file.name}
                  </span>
                  <span className="preview-size">{formatBytes(file.size)}</span>
                  <button
                    type="button"
                    className="preview-remove"
                    onClick={clearFile}
                  >
                    移除
                  </button>
                </div>
              </div>
            )}
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

        <div className="field">
          <span>影片時長</span>
          <div className="duration">
            {[5, 10].map((d) => (
              <button
                key={d}
                type="button"
                className={duration === d ? "active" : ""}
                onClick={() => setDuration(d)}
              >
                {d} 秒
              </button>
            ))}
          </div>
          {duration === 10 && (
            <span className="hint">10 秒約為 5 秒的 2 倍費用</span>
          )}
        </div>

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
