import type {
  ApiErrorEnvelope,
  BackgroundRunRecord,
  HealthResponse,
  SnapshotSummary,
} from "../types/api";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { headers: { Accept: "application/json" }, signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("The local decision engine is not reachable.", 0);
  }
  if (!response.ok) {
    let body: ApiErrorEnvelope | undefined;
    try {
      body = (await response.json()) as ApiErrorEnvelope;
    } catch {
      // The backend contract normally supplies JSON; retain a safe generic fallback.
    }
    throw new ApiError(body?.error.message ?? `Request failed (${response.status}).`, response.status, body?.error.code);
  }
  return (await response.json()) as T;
}

export const api = {
  health: (signal?: AbortSignal) => getJson<HealthResponse>("/api/v1/health", signal),
  snapshots: (signal?: AbortSignal) => getJson<readonly SnapshotSummary[]>("/api/v1/snapshots", signal),
  snapshot: (snapshotId: string, signal?: AbortSignal) =>
    getJson<SnapshotSummary>(`/api/v1/snapshots/${encodeURIComponent(snapshotId)}`, signal),
  runs: (signal?: AbortSignal) => getJson<readonly BackgroundRunRecord[]>("/api/v1/runs?limit=50", signal),
};
