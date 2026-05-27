export interface CardPayload {
  word: string;
  word_reading: string;
  word_meaning: string;
  expression_furigana: string;
  sentence: string;
  sentence_bold: string;
  sentence_anki: string;
  sentence_reading: string;
  sentence_meaning: string;
  context_note: string;
  sentence_audio_filename: string;
  sentence_audio_tag: string;
}

export interface GenerateResponse {
  card: CardPayload;
  anki_tsv: string;
  import_notes: string[];
  sentence_audio_base64: string;
}

export interface HealthResponse {
  ok: boolean;
  llm_provider: string;
  base_url: string;
  model: string;
  server_running: boolean;
  model_available: boolean;
  model_cached?: boolean;
  model_loading?: boolean;
  model_loaded_in_memory?: boolean;
  available_models: string[];
  setup_hint: string | null;
  ollama_mlx_crash_note: string | null;
  tts_voice: string;
  anki_deck_name?: string;
  anki_model_name?: string;
}

const HEALTH_TIMEOUT_MS = 60_000;

export async function fetchHealth(): Promise<HealthResponse> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
  try {
    const res = await fetch("/api/health", { signal: controller.signal });
    if (!res.ok) throw new Error(`Health check failed (${res.status})`);
    return res.json();
  } finally {
    clearTimeout(timer);
  }
}

export async function generateCard(word: string): Promise<GenerateResponse> {
  const res = await fetch("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ word }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = err.detail;
    throw new Error(
      typeof detail === "string" ? detail : res.statusText || "Generation failed"
    );
  }
  return res.json();
}

export async function uploadApkg(file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/upload-apkg", { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Upload failed");
  }
  const data = await res.json();
  return data.task_id;
}

export interface TaskStatus {
  status: string;
  error?: string;
  paused?: boolean;
  words?: string[];
  current_index?: number;
  completed_words?: string[];
  failed_words?: Record<string, string>;
  skipped_words?: string[];
}

export async function controlTask(
  taskId: string,
  action: "pause" | "resume" | "skip",
  index?: number
): Promise<{ ok: boolean }> {
  const res = await fetch(`/api/task/${taskId}/control`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, index }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Control request failed");
  }
  return res.json();
}

export async function pollTask(taskId: string, signal?: AbortSignal): Promise<TaskStatus> {
  const res = await fetch(`/api/task/${taskId}`, { signal });
  if (!res.ok) throw new Error("Task lookup failed");
  return res.json();
}

export async function previewTaskWord(taskId: string, word: string): Promise<GenerateResponse> {
  const res = await fetch(`/api/task/${taskId}/preview/${encodeURIComponent(word)}`);
  if (!res.ok) throw new Error("Preview not available");
  return res.json();
}

export async function downloadTaskApkg(taskId: string): Promise<Blob> {
  const res = await fetch(`/api/task/${taskId}/download`);
  if (!res.ok) throw new Error("Download failed");
  return res.blob();
}

export async function addToAnki(word: string): Promise<{ success: boolean; note_id?: number }> {
  const res = await fetch("/api/add-to-anki", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ word }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to add to Anki");
  }
  return res.json();
}

export async function addToAnkiBatch(words: string[]): Promise<{ added: number; failed: number; errors: string[] }> {
  const res = await fetch("/api/add-to-anki/batch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ words }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Batch add failed");
  }
  return res.json();
}

export async function downloadZip(word: string): Promise<Blob> {
  const res = await fetch("/api/generate/download", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ word }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = err.detail;
    throw new Error(
      typeof detail === "string" ? detail : res.statusText || "Download failed"
    );
  }
  return res.blob();
}
