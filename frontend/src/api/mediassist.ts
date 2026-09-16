import type {
  AnalyzeResponse,
  DoctorSearchParams,
  DoctorSearchResponse,
  ConversationResponse,
  FollowUpQuestion,
  SelfExamInstruction,
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

export async function startSession(data: FormData): Promise<ConversationResponse> {
  try {
    const res = await request<ConversationResponse>("/session/start", { method: "POST", body: data });
    return res;
  } catch (err) {
    console.warn("Backend /session/start not available. Using interactive mock.", err);
    await new Promise((r) => setTimeout(r, 1500));
    return {
      session_id: "mock-session-" + Date.now(),
      status: "needs_followup",
      turn: 1,
      initial_analysis: "I noticed you mentioned swelling in your legs and back pain. To give you the best assessment, I need to ask a few clarifying questions.",
      questions: [
        {
          id: "q1",
          text: "Is the swelling in one leg or both legs?",
          type: "multiple_choice",
          options: ["One leg", "Both legs", "Not sure"]
        },
        {
          id: "q2",
          text: "Does the back pain radiate down your legs?",
          type: "yes_no"
        }
      ],
      self_exams: [
        {
          id: "exam1",
          title: "Check for pitting edema",
          why_useful: "Press firmly on the swollen area of your leg for 5 seconds. If a dent remains, it indicates pitting edema."
        }
      ],
      disclaimer: "Mock mode",
      processing_time_ms: 1500
    };
  }
}

export async function respondSession(sessionId: string, answers: Record<string, string>): Promise<ConversationResponse> {
  try {
    const formData = new FormData();
    formData.append("session_id", sessionId);
    formData.append("answers", JSON.stringify(answers));
    const res = await request<ConversationResponse>("/session/respond", { method: "POST", body: formData });
    return res;
  } catch (err) {
    console.warn("Backend /session/respond not available. Using interactive mock.", err);
    await new Promise((r) => setTimeout(r, 1500));
    
    // After 1 question turn, return a complete diagnosis!
    return {
      session_id: sessionId,
      status: "complete",
      turn: 2,
      diagnosis: {
        condition_name: "Possible Sciatica or Fluid Retention",
        confidence: 85,
        severity_level: "moderate",
        specialist_needed: "General Physician",
        explanation: "Based on the swelling and back pain, combined with your answers, this could be related to fluid retention or nerve pressure.",
        citations: []
      },
      urgency: {
        level: "moderate",
        action_plan: ["Rest with legs elevated", "Monitor for shortness of breath", "Schedule a doctor visit"],
        call_emergency: false
      },
      disclaimer: "Mock mode",
      processing_time_ms: 1500
    };
  }
}
