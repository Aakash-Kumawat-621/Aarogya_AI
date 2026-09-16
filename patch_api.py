import os

code = '''
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
'''

with open('frontend/src/api/mediassist.ts', 'r', encoding='utf-8') as f:
    content = f.read()

# Add imports for the new types
content = content.replace(
    'DoctorSearchResponse,',
    'DoctorSearchResponse,\n  ConversationResponse,\n  FollowUpQuestion,\n  SelfExamInstruction,'
)

with open('frontend/src/api/mediassist.ts', 'w', encoding='utf-8') as f:
    f.write(content + "\n" + code)

print("Updated mediassist.ts")
