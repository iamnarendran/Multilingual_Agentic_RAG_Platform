import { API_URL, ApiError, getToken } from "./api";

export type ServerEvent = { event: string; data: Record<string, unknown> };

/**
 * POST /api/chat and yield Server-Sent Events as they arrive.
 * (EventSource can't send a POST body or auth header, so we read the stream ourselves.)
 */
export async function* streamChat(
  body: { message: string; conversation_id?: string | null; document_ids?: string[] | null },
  signal: AbortSignal,
): AsyncGenerator<ServerEvent> {
  const token = getToken();
  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(`Can't reach the server at ${API_URL}. Check that the backend is running.`, 0);
  }
  if (!response.ok || !response.body) {
    let message = `Request failed (${response.status}).`;
    try {
      const detail = (await response.json()).detail;
      if (typeof detail === "string") message = detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(message, response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      let event = "message";
      const dataLines: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
      }
      if (!dataLines.length) continue;
      try {
        yield { event, data: JSON.parse(dataLines.join("\n")) };
      } catch {
        /* skip malformed event */
      }
    }
  }
}
