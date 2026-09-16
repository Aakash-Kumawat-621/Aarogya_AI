export interface PatientProfile {
  name: string;
  age: number;
  gender: "male" | "female" | "other";
  blood_group?: string;
  height_cm?: number;
  weight_kg?: number;
  conditions?: string[];
  allergies?: string[];
  medications?: string[];
  smoking?: "never" | "former" | "current";
  pack_years?: number;
  alcohol_units_per_week?: number;
  activity_level?: "sedentary" | "light" | "moderate" | "active";
  sleep_hours?: number;
}

export interface Diagnosis {
  condition_name: string;
  confidence: number;
  explanation: string;
  severity_level: string;
  specialist_needed: string;
  citations: string[];
}

export interface Urgency {
  level: "emergency" | "urgent" | "moderate" | "low";
  action_plan: string[];
  call_emergency: boolean;
}

export interface DoctorResult {
  name: string;
  specialty: string;
  address: string;
  distance_km: number;
  rating?: number;
  phone?: string;
  is_open_now?: boolean;
  source: string;
}

export interface AnalyzeResponse {
  session_id: string;
  context_built: boolean;
  inputs_processed: string[];
  symptoms_extracted: number;
  risk_flags: string[];
  context_confidence: number;
  primary_concern: string;
  diagnosis?: Diagnosis;
  urgency?: Urgency;
  recommendations?: DoctorResult[];
  disclaimer: string;
  processing_time_ms: number;
}

export interface DoctorSearchParams {
  condition: string;
  lat?: number;
  lng?: number;
  radius_km?: number;
}

export interface DoctorSearchResponse {
  specialty: string;
  doctors: DoctorResult[];
  condition: string;
}
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
