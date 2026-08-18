// Empty by default: same origin, no CORS. Paths below carry the /api prefix
// rather than relying on an env var, because a .env file cannot be trusted to
// reach the build — .env.production is gitignored, so the first Vercel deploy
// built with this undefined, called /ask, got routed to the Next.js service and
// rendered its 404 page into the answer box.
//
// /api works on every host we deploy to: Vercel Services routes /api/* to the
// Python service, and when FastAPI serves this UI itself the same routes are
// registered under both '' and '/api' (see echorag/api.py).
//
// Local dev sets NEXT_PUBLIC_API_URL=http://localhost:8000 in .env.local.
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

/** A readable one-liner from a failed response — never a page of markup.
 *
 * Routing mistakes return an HTML error page, and printing that verbatim filled
 * the answer box with a Next.js 404 document. Prefer FastAPI's JSON `detail`,
 * fall back to the status, and never surface raw HTML. */
async function failureMessage(res: Response): Promise<string> {
  const body = await res.text().catch(() => "");
  const looksLikeHtml = /^\s*<(!doctype|html)/i.test(body);

  if (body && !looksLikeHtml) {
    try {
      const parsed = JSON.parse(body);
      if (typeof parsed?.detail === "string") return parsed.detail;
    } catch {
      // Not JSON — fall through and use the text, trimmed.
    }
    return body.slice(0, 200);
  }
  return `${res.status} ${res.statusText || "request failed"}`;
}

async function post(path: string, body: FormData): Promise<Result> {
  const res = await fetch(`${API_URL}${path}`, { method: "POST", body });
  if (!res.ok) throw new Error(await failureMessage(res));
  return res.json();
}

export function askText(text: string) {
  const fd = new FormData();
  fd.append("text", text);
  return post("/api/ask", fd);
}

export function askVoice(audio: Blob) {
  const fd = new FormData();
  // Sarvam infers the container from the filename, so name it explicitly.
  fd.append("audio", audio, "query.webm");
  return post("/api/ask-voice", fd);
}
