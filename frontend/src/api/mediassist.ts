import type {
  AnalyzeResponse,
  DoctorSearchParams,
  DoctorSearchResponse,
} from "@/types/api.types";

const API_BASE_URL =
  import.meta.env["VITE_API_BASE_URL"] ||
  "https://zilbjmvwx1.execute-api.us-east-1.amazonaws.com/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`Aarogya AI request failed with status ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export async function checkHealth(): Promise<unknown> {
  return request("/health");
}

export async function analyzeSymptoms(data: FormData): Promise<AnalyzeResponse> {
  return request<AnalyzeResponse>("/analyze", { method: "POST", body: data });
}

export async function searchDoctors(
  params: DoctorSearchParams,
): Promise<DoctorSearchResponse> {
  const query = new URLSearchParams({ condition: params.condition });
  if (params.lat !== undefined) query.set("lat", String(params.lat));
  if (params.lng !== undefined) query.set("lng", String(params.lng));
  if (params.radius_km !== undefined) query.set("radius_km", String(params.radius_km));
  return request<DoctorSearchResponse>(`/doctors?${query.toString()}`);
}

export async function getSession(id: string): Promise<AnalyzeResponse> {
  return request<AnalyzeResponse>(`/sessions/${encodeURIComponent(id)}`);
}

export async function getHistory(): Promise<AnalyzeResponse[]> {
  return request<AnalyzeResponse[]>("/history");
}

export async function submitFeedback(
  sessionId: string,
  rating: 1 | -1,
  comment?: string,
): Promise<void> {
  await request<void>(`/sessions/${encodeURIComponent(sessionId)}/feedback`, {
    method: "POST",
    body: JSON.stringify({ rating, comment }),
  });
}