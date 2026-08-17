// Empty by default so requests go to the same origin — in production FastAPI
// serves this UI and the API together, so "/ask" is correct and there is no
// CORS. Local dev sets NEXT_PUBLIC_API_URL=http://localhost:8000 in .env.local,
// because there the two run on different ports.
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export type Spans = Record<string, number>;

export type Result = {
  type: "answer" | "abstention";
  text: string;
  transcript: string;
  spans: Spans;
  stt_ms: number | null;
  slo_ms: number;
  reason?: string;
  confidence?: number;
  citations?: string[];
  source?: string;
};

async function post(path: string, body: FormData): Promise<Result> {
  const res = await fetch(`${API_URL}${path}`, { method: "POST", body });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export function askText(text: string) {
  const fd = new FormData();
  fd.append("text", text);
  return post("/ask", fd);
}

export function askVoice(audio: Blob) {
  const fd = new FormData();
  // Sarvam infers the container from the filename, so name it explicitly.
  fd.append("audio", audio, "query.webm");
  return post("/ask-voice", fd);
}
