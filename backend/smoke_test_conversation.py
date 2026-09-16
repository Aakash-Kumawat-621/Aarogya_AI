from app.modules.conversation.self_exam_guide import SELF_EXAM_LIBRARY, get_exams_for_differential
from app.modules.conversation.confidence_evaluator import should_diagnose, check_emergency_bypass
from app.modules.conversation.question_generator import _fallback_questions
from app.modules.conversation.session_manager import build_enriched_symptoms_text
from app.api.routes.conversation import router

exams = get_exams_for_differential(["ACS", "Panic Attack"])
print("Self-exams for ACS/Panic Attack:", [e["id"] for e in exams])

fallback = _fallback_questions([], [])
print("Fallback questions:", len(fallback["questions"]), "questions")

print("All conversation module checks passed!")
