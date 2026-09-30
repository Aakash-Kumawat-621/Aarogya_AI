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
  return request<DoctorSearchResponse>(`/doctors/search?${query.toString()}`);
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

    // Extract symptoms from the submitted form to generate relevant mock questions
    const symptomsText = (data.get("symptoms_text") as string || "").toLowerCase();

    // Detect symptom categories and generate relevant follow-ups
    const isMentalHealth = /depress|anxiet|sad|stress|panic|insomnia|sleep|mood|suicid|lonely|hopeless|motivation|mental/i.test(symptomsText);
    const isRespiratory = /cough|breath|chest|wheez|lung|asthma/i.test(symptomsText);
    const isDigestive = /stomach|nausea|vomit|diarr|abdomen|bloat|digest/i.test(symptomsText);
    const isNeurological = /headache|dizzy|migraine|vision|numb|tingl|seizure/i.test(symptomsText);

    let questions: FollowUpQuestion[];
    let analysis: string;

    if (isMentalHealth) {
      analysis = "I understand you're experiencing emotional or mental health symptoms. Let me ask a few questions to better understand your situation.";
      questions = [
        { id: "q1", text: "How long have you been feeling this way?", type: "multiple_choice", options: ["Less than 2 weeks", "2–4 weeks", "1–3 months", "More than 3 months"] },
        { id: "q2", text: "Have these feelings affected your ability to work, study, or manage daily tasks?", type: "yes_no" },
        { id: "q3", text: "Have you experienced changes in your appetite or sleep patterns?", type: "multiple_choice", options: ["Sleep problems only", "Appetite changes only", "Both", "Neither"] },
      ];
    } else if (isRespiratory) {
      analysis = "I see you're experiencing respiratory symptoms. Let me gather more details.";
      questions = [
        { id: "q1", text: "Do you have a fever along with these symptoms?", type: "yes_no" },
        { id: "q2", text: "How would you describe the cough?", type: "multiple_choice", options: ["Dry cough", "Cough with mucus", "Cough with blood", "No cough"] },
      ];
    } else if (isDigestive) {
      analysis = "I notice you're experiencing digestive symptoms. A few more details will help.";
      questions = [
        { id: "q1", text: "When did these symptoms start?", type: "multiple_choice", options: ["Today", "1–3 days ago", "This week", "More than a week ago"] },
        { id: "q2", text: "Have you noticed any blood in your stool or vomit?", type: "yes_no" },
      ];
    } else if (isNeurological) {
      analysis = "I see you're experiencing neurological symptoms. Let me ask a few clarifying questions.";
      questions = [
        { id: "q1", text: "Is the pain or symptom on one side of the body or both?", type: "multiple_choice", options: ["Left side only", "Right side only", "Both sides", "Changes sides"] },
        { id: "q2", text: "Did the symptoms start suddenly or gradually?", type: "multiple_choice", options: ["Suddenly (within minutes)", "Over a few hours", "Over a few days", "Gradually (weeks)"] },
      ];
    } else {
      analysis = "Thank you for sharing your symptoms. Let me ask a few follow-up questions to better understand your condition.";
      questions = [
        { id: "q1", text: "On a scale of 1–10, how severe are your symptoms right now?", type: "multiple_choice", options: ["1–3 (mild)", "4–6 (moderate)", "7–9 (severe)", "10 (worst ever)"] },
        { id: "q2", text: "How long have you been experiencing these symptoms?", type: "multiple_choice", options: ["Less than 1 hour", "1–24 hours", "1–7 days", "More than 1 week"] },
        { id: "q3", text: "Do the symptoms come and go, or are they constant?", type: "multiple_choice", options: ["Constant", "Come and go", "Getting worse", "Getting better"] },
      ];
    }

    return {
      session_id: "mock-session-" + Date.now(),
      status: "needs_followup",
      turn: 1,
      initial_analysis: analysis,
      questions,
      self_exams: [],
      disclaimer: "Demo mode — connect to the live backend for AI-powered analysis",
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
    
    return {
      session_id: sessionId,
      status: "complete",
      turn: 2,
      diagnosis: {
        condition_name: "Assessment Complete",
        confidence: 70,
        severity_level: "moderate",
        specialist_needed: "General Physician",
        explanation: "Based on your symptoms and answers, we recommend consulting a healthcare professional for a thorough evaluation. This is a demo assessment — the live AI backend provides more accurate, personalized results.",
        citations: []
      },
      urgency: {
        level: "moderate",
        action_plan: ["Schedule a visit with your doctor within the next few days", "Keep track of your symptoms and note any changes", "Stay hydrated and get adequate rest"],
        call_emergency: false
      },
      disclaimer: "Demo mode — connect to the live backend for AI-powered analysis",
      processing_time_ms: 1500
    };
  }
}
