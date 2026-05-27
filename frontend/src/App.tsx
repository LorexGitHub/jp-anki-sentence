import { useEffect, useMemo, useState } from "react";
import {
  addToAnki,
  addToAnkiBatch,
  controlTask,
  downloadTaskApkg,
  downloadZip,
  fetchHealth,
  generateCard,
  pollTask,
  previewTaskWord,
  uploadApkg,
  type GenerateResponse,
  type HealthResponse,
} from "./api";

interface BatchState {
  taskId: string | null;
  status: string;
  error: string | null;
  words: string[];
  currentIndex: number;
  completed: string[];
  failed: Record<string, string>;
  skipped: string[];
  paused: boolean;
  filter: string;
  selectedWord: string | null;
  preview: GenerateResponse | null;
  previewLoading: boolean;
}

const initialBatch: BatchState = {
  taskId: null,
  status: "",
  error: null,
  words: [],
  currentIndex: -1,
  completed: [],
  failed: {},
  skipped: [],
  paused: false,
  filter: "",
  selectedWord: null,
  preview: null,
  previewLoading: false,
};

export default function App() {
  const [word, setWord] = useState("元気");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GenerateResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [ankiAdding, setAnkiAdding] = useState(false);
  const [batch, setBatch] = useState<BatchState>(initialBatch);
  const [expandedErrWord, setExpandedErrWord] = useState<string | null>(null);
  const [addingAll, setAddingAll] = useState(false);

  async function refreshHealth() {
    setHealthLoading(true);
    try {
      setHealth(await fetchHealth());
    } catch (e) {
      const timedOut =
        e instanceof DOMException && e.name === "AbortError";
      setHealth({
        ok: false,
        llm_provider: "huggingface",
        base_url: "http://127.0.0.1:8000",
        model: "tencent/Hy-MT2-1.8B",
        server_running: false,
        model_available: false,
        available_models: [],
        setup_hint: timedOut
          ? "Backend timed out. Start uvicorn on port 8000 (see README)."
          : "Cannot reach backend. Run: cd backend && uvicorn app.main:app --reload --port 8000",
        ollama_mlx_crash_note: null,
        tts_voice: "",
      });
    } finally {
      setHealthLoading(false);
    }
  }

  useEffect(() => {
    refreshHealth();
    const interval = setInterval(refreshHealth, 15_000);
    return () => clearInterval(interval);
  }, []);

  const audioUrl = useMemo(() => {
    if (!result?.sentence_audio_base64) return null;
    return `data:audio/mpeg;base64,${result.sentence_audio_base64}`;
  }, [result]);

  const llmReady =
    health?.server_running &&
    (health?.llm_provider === "huggingface" ||
      health?.model_available ||
      health?.available_models.length === 0);

  const modelLoading = health?.model_loading;

  async function handleGenerate() {
    setError(null);
    setLoading(true);
    setResult(null);
    try {
      const data = await generateCard(word.trim());
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function handleAddToAnki() {
    if (!result) return;
    setError(null);
    setAnkiAdding(true);
    try {
      await addToAnki(word.trim());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add to Anki");
    } finally {
      setAnkiAdding(false);
    }
  }

  async function handleDownload() {
    setError(null);
    setLoading(true);
    try {
      // Instant if user already generated this word (server cache)
      const blob = await downloadZip(word.trim());
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `anki_${word.trim() || "card"}.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Download failed");
    } finally {
      setLoading(false);
    }
  }

  async function copyTsv() {
    if (!result) return;
    await navigator.clipboard.writeText(result.anki_tsv);
  }

  function updateBatch(partial: Partial<BatchState>) {
    setBatch(prev => ({ ...prev, ...partial }));
  }

  function resetBatch() {
    setBatch(initialBatch);
  }

  async function loadPreview(word: string) {
    if (!batch.taskId) return;
    updateBatch({ selectedWord: word, previewLoading: true, preview: null });
    try {
      const data = await previewTaskWord(batch.taskId, word);
      updateBatch({ preview: data, previewLoading: false });
    } catch {
      updateBatch({ previewLoading: false });
    }
  }

  async function handleUploadApkg(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    resetBatch();
    updateBatch({ status: "Uploading…" });
    e.target.value = "";
    try {
      const taskId = await uploadApkg(file);
      updateBatch({ taskId, status: "Extracting words…" });
      const poll = async () => {
        const state = await pollTask(taskId);
        updateBatch({
          words: state.words ?? [],
          currentIndex: state.current_index ?? -1,
          completed: state.completed_words ?? [],
          failed: state.failed_words ?? {},
          skipped: state.skipped_words ?? [],
          paused: state.paused ?? false,
        });
        if (state.status === "done") {
          updateBatch({ status: "Complete" });
          const blob = await downloadTaskApkg(taskId);
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = "jp_sentences.apkg";
          a.click();
          URL.revokeObjectURL(url);
        } else if (state.status === "error") {
          updateBatch({ status: "", error: state.error || "Processing failed" });
        } else {
          setTimeout(poll, 2000);
        }
      };
      poll();
    } catch (e) {
      updateBatch({ status: "", error: e instanceof Error ? e.message : "Upload failed" });
    }
  }

  const filteredWords = useMemo(() => {
    if (!batch.filter) return batch.words;
    return batch.words.filter(w => w.includes(batch.filter));
  }, [batch.words, batch.filter]);

  function wordStatusText(word: string, idx: number): "pending" | "processing" | "done" | "failed" | "skipped" {
    if (batch.failed[word]) return "failed";
    if (batch.completed.includes(word)) return "done";
    if (batch.skipped.includes(word)) return "skipped";
    if (idx === batch.currentIndex) return "processing";
    return "pending";
  }

  async function handlePause() {
    if (!batch.taskId) return;
    try {
      await controlTask(batch.taskId, "pause");
      updateBatch({ paused: true });
    } catch (e) {
      updateBatch({ error: e instanceof Error ? e.message : "Pause failed" });
    }
  }

  async function handleResume() {
    if (!batch.taskId) return;
    try {
      await controlTask(batch.taskId, "resume");
      updateBatch({ paused: false });
    } catch (e) {
      updateBatch({ error: e instanceof Error ? e.message : "Resume failed" });
    }
  }

  async function handleSkipTo(index: number) {
    if (!batch.taskId) return;
    try {
      await controlTask(batch.taskId, "skip", index);
      updateBatch({ paused: false });
    } catch (e) {
      updateBatch({ error: e instanceof Error ? e.message : "Skip failed" });
    }
  }

  async function handleAddAll() {
    setAddingAll(true);
    try {
      const result = await addToAnkiBatch(batch.completed);
      const msg = `Added ${result.added} card(s)`;
      const parts = [msg];
      if (result.failed > 0) parts.push(`${result.failed} failed`);
      if (result.errors.length > 0) parts.push(`${result.errors.length} error(s): ${result.errors[0]}`);
      updateBatch({ error: parts.join(", ") });
    } catch (e) {
      updateBatch({ error: e instanceof Error ? e.message : "Batch add failed" });
    }
    setAddingAll(false);
  }

  return (
    <>
      <h1>JP Anki Sentence</h1>
      <p className="subtitle">
        Enter a Japanese word — get a natural example sentence with furigana,
        audio, and a one-click Anki import pack. Uses a local Hugging Face model
        (auto-downloads on first run).
      </p>

      <div className="llm-status">
        {healthLoading ? (
          <p className="key-hint">Checking backend…</p>
        ) : modelLoading ? (
          <>
            <p className="key-hint">
              <span className="status-dot loading" />
              Loading model into memory — first card may take a minute…
            </p>
          </>
        ) : llmReady ? (
          <>
            <p className="key-hint">
              <span className="status-dot ok" />
              Backend ready — <code>{health?.model}</code>
              {health?.model_loaded_in_memory && " (model in memory)"}
              {health?.model_cached && !health?.model_loaded_in_memory && " (cached on disk)"}
            </p>
            {health?.setup_hint && (
              <p className="key-hint">{health.setup_hint}</p>
            )}
          </>
        ) : (
          <>
            <p className="key-hint warn-box">
              <span className="status-dot warn" />
              {health.setup_hint ||
                (health.llm_provider === "ollama"
                  ? `Start Ollama and run: ollama pull ${health.model}`
                  : health.llm_provider === "huggingface"
                    ? "pip install torch transformers accelerate huggingface_hub"
                    : "Start LM Studio server and load a model.")}
            </p>
            {health?.ollama_mlx_crash_note && (
              <p className="key-hint">{health.ollama_mlx_crash_note}</p>
            )}
            <button
              type="button"
              className="btn-secondary"
              style={{ marginTop: "0.5rem" }}
              onClick={refreshHealth}
            >
              Retry connection
            </button>
          </>
        )}
      </div>

      <div className="field">
        <label htmlFor="word">Japanese word</label>
        <input
          id="word"
          type="text"
          value={word}
          onChange={(e) => setWord(e.target.value)}
          placeholder="例: 元気、食べる、勉強"
          onKeyDown={(e) => e.key === "Enter" && !loading && llmReady && handleGenerate()}
        />
      </div>

      <button
        className="btn-primary"
        disabled={loading || !word.trim() || !llmReady}
        onClick={handleGenerate}
      >
        {loading
          ? "Generating… (first run can take several minutes)"
          : "Generate example sentence"}
      </button>

      {error && <div className="error">{error}</div>}

      {result && (
        <section className="card-preview">
          <h2>Card Preview</h2>

          <div className="card-face front">
            <h3 className="face-label">Front</h3>
            <span
              className="field-value japanese-large"
              dangerouslySetInnerHTML={{ __html: result.card.sentence_bold }}
            />
          </div>

          <div className="card-divider" />

          <div className="card-face back">
            <h3 className="face-label">Back (reveal)</h3>
            <div className="card-field">
              <span className="field-label">Sentence</span>
              <span className="field-value japanese-large">{result.card.sentence}</span>
            </div>
            <div className="card-field">
              <span className="field-label">Hiragana</span>
              <span className="field-value japanese-large">{result.card.sentence_reading}</span>
            </div>
            <div className="card-field">
              <span className="field-label">Translation</span>
              <span className="field-value">{result.card.sentence_meaning}</span>
            </div>
            {audioUrl && (
              <div className="audio-row" style={{ marginTop: "0.75rem" }}>
                <span className="field-label">Audio</span>
                <audio controls src={audioUrl} />
              </div>
            )}
          </div>

          <div className="actions">
            <button
              className="btn-primary"
              type="button"
              disabled={ankiAdding}
              onClick={handleAddToAnki}
            >
              {ankiAdding ? "Adding…" : "Add to Anki"}
            </button>
            <button className="btn-secondary" type="button" onClick={copyTsv}>
              Copy TSV
            </button>
            <button
              className="btn-secondary"
              type="button"
              disabled={loading}
              onClick={handleDownload}
            >
              Download ZIP
            </button>
          </div>
        </section>
      )}

      <section className="card-preview" style={{ marginTop: "2rem" }}>
        <h2>Batch from .apkg</h2>
        <p className="key-hint">
          Upload an Anki .apkg export — extracts all Lapis words, generates sentences + audio, and downloads a new .apkg.
        </p>

        {/* Upload — hide while running so user can't double-trigger */}
        {(!batch.taskId || batch.status === "Complete" || batch.error) && (
          <label className="file-label">
            <input
              type="file"
              accept=".apkg"
              onChange={handleUploadApkg}
              style={{ display: "none" }}
            />
            <span className="btn-primary" style={{ display: "inline-block", cursor: "pointer" }}>
              {batch.taskId ? "Choose another .apkg" : "Choose .apkg file"}
            </span>
          </label>
        )}

        {batch.status && <p className="key-hint" style={{ marginTop: "0.5rem" }}>{batch.status}</p>}
        {batch.error && <div className="error">{batch.error}</div>}

        {/* Word list */}
        {batch.words.length > 0 && (
          <>
            <input
              type="text"
              placeholder="Filter words…"
              value={batch.filter}
              onChange={e => updateBatch({ filter: e.target.value })}
              style={{ marginTop: "0.75rem" }}
            />

            <div className="batch-stats">
              {batch.words.length} words
              {batch.currentIndex >= 0 && <span> &middot; processing {batch.currentIndex + 1}/{batch.words.length}</span>}
              {batch.completed.length > 0 && <span> &middot; {batch.completed.length} passed</span>}
              {Object.keys(batch.failed).length > 0 && <span> &middot; {Object.keys(batch.failed).length} failed</span>}
              {batch.skipped.length > 0 && <span> &middot; {batch.skipped.length} skipped</span>}
              {batch.status === "Complete" && <span> &middot; done</span>}
              {batch.status === "paused" && <span> &middot; paused</span>}
              {(batch.status === "processing" || batch.status === "paused") && (
                <button
                  className="btn-small"
                  style={{ marginLeft: "0.5rem" }}
                  onClick={batch.paused ? handleResume : handlePause}
                >
                  {batch.paused ? "Go" : "Pause"}
                </button>
              )}
            </div>

            <div className="batch-word-list">
              {filteredWords.map((w) => {
                const globalIdx = batch.words.indexOf(w);
                const status = wordStatusText(w, globalIdx);
                const canPreview = status === "done" || status === "failed";
                const isFailed = status === "failed";
                const showErr = isFailed && expandedErrWord === w;
                const isRunning = batch.status === "processing" || batch.status === "paused";
                return (
                  <div key={w}>
                    <div
                      className={"batch-word-row" + (canPreview ? " clickable" : "") + (w === batch.selectedWord ? " selected" : "")}
                      onClick={() => canPreview && !isFailed && loadPreview(w)}
                    >
                      <span
                        className={"word-index" + (isRunning ? " clickable" : "")}
                        title={isRunning ? `Start from word ${globalIdx + 1}` : ""}
                        onClick={e => { if (isRunning) { e.stopPropagation(); handleSkipTo(globalIdx); } }}
                      >
                        {globalIdx + 1}
                      </span>
                      <span className={"status-dot " + status} />
                      <span className="batch-word-text">{w}</span>
                      {isFailed && (
                        <span
                          className="batch-word-err"
                          onClick={e => { e.stopPropagation(); setExpandedErrWord(showErr ? null : w); }}
                          title={batch.failed[w]}
                        >!</span>
                      )}
                    </div>
                    {showErr && (
                      <div className="batch-error-detail">{batch.failed[w]}</div>
                    )}
                  </div>
                );
              })}
              {filteredWords.length === 0 && (
                <p className="key-hint" style={{ padding: "0.5rem 0" }}>No matching words</p>
              )}
            </div>

            {batch.completed.length > 0 && (
              <div className="actions" style={{ marginTop: "0.75rem" }}>
                <button
                  className="btn-primary"
                  disabled={addingAll}
                  onClick={handleAddAll}
                >
                  {addingAll
                    ? "Adding…"
                    : `Add All Passed (${batch.completed.length}/${batch.words.length} to Anki)`}
                </button>
                <button
                  className="btn-secondary"
                  disabled={batch.status !== "Complete"}
                  onClick={async () => {
                    if (!batch.taskId) return;
                    const blob = await downloadTaskApkg(batch.taskId);
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = "jp_sentences.apkg";
                    a.click();
                    URL.revokeObjectURL(url);
                  }}
                >
                  Download .apkg
                </button>
              </div>
            )}
          </>
        )}

        {/* Preview for selected batch word */}
        {batch.preview && (
          <div className="batch-preview">
            <div className="card-divider" />
            <h2 style={{ opacity: 0.5 }}>{batch.selectedWord}</h2>
            <div className="card-face front">
              <h3 className="face-label">Front</h3>
              <span
                className="field-value japanese-large"
                dangerouslySetInnerHTML={{ __html: batch.preview.card.sentence_bold }}
              />
            </div>
            <div className="card-divider" />
            <div className="card-face back">
              <h3 className="face-label">Back</h3>
              <div className="card-field">
                <span className="field-label">Sentence</span>
                <span className="field-value japanese-large">{batch.preview.card.sentence}</span>
              </div>
              <div className="card-field">
                <span className="field-label">Hiragana</span>
                <span className="field-value japanese-large">{batch.preview.card.sentence_reading}</span>
              </div>
              <div className="card-field">
                <span className="field-label">Translation</span>
                <span className="field-value">{batch.preview.card.sentence_meaning}</span>
              </div>
              {batch.preview.sentence_audio_base64 && (
                <div className="audio-row" style={{ marginTop: "0.75rem" }}>
                  <span className="field-label">Audio</span>
                  <audio controls src={`data:audio/mpeg;base64,${batch.preview.sentence_audio_base64}`} />
                </div>
              )}
            </div>
            <div className="actions">
              <button
                className="btn-primary"
                type="button"
                disabled={ankiAdding}
                onClick={async () => {
                  try {
                    await addToAnki(batch.selectedWord!);
                  } catch (e) {
                    updateBatch({ error: e instanceof Error ? e.message : "Failed to add" });
                  }
                }}
              >
                {ankiAdding ? "Adding…" : "Add to Anki"}
              </button>
            </div>
          </div>
        )}
        {batch.previewLoading && <p className="key-hint" style={{ marginTop: "0.5rem" }}>Loading preview…</p>}
      </section>

      <aside className="import-tips">
        <strong>Anki import</strong>
        <ul>
          <li><b>Add to Anki</b> — one-click, requires <a href="https://ankiweb.net/shared/info/2055492159" target="_blank">AnkiConnect</a> plugin</li>
          <li>Or download the ZIP, then File → Import → <code>anki_import.tsv</code></li>
          <li>Audio files are embedded in the ZIP as MP3</li>
        </ul>
      </aside>
    </>
  );
}
