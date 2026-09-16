import os

with open('frontend/src/types/api.types.ts', 'a', encoding='utf-8') as f:
    f.write('''
export interface FollowUpQuestion {
  id: string;
  text: string;
  type: "yes_no" | "multiple_choice";
  options?: string[];
}

export interface SelfExamInstruction {
  id: string;
  title: string;
  why_useful: string;
}

export interface ConversationResponse {
  session_id: string;
  status: "needs_followup" | "complete";
  turn: number;
  initial_analysis?: string;
  questions?: FollowUpQuestion[];
  self_exams?: SelfExamInstruction[];
  diagnosis?: Diagnosis;
  urgency?: Urgency;
  recommendations?: DoctorResult[];
  disclaimer: string;
  processing_time_ms: number;
}
''')
print("Patched types.")
