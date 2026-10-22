"""
GramCare – Rule-based triage assistant
POST /api/v1/triage/evaluate  – evaluate symptoms/vitals against red-flag rules

Output is labelled 'advice only'. All rules are deterministic (no ML).
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CHWOrAbove, get_db
from app.models.models import TriageRule
from app.schemas.schemas import TriageEvalRequest, TriageEvalResponse, TriageFlag, VitalsSchema

router = APIRouter(prefix="/triage", tags=["Triage"])

# Hard-coded fallback rules (also seeded in DB via migrations)
BUILT_IN_RULES = [
    {
        "name": "Low SpO2",
        "severity": "red",
        "advice": "URGENT: SpO2 below 90%. Refer to hospital immediately.",
        "condition": lambda symptoms, vitals: vitals and vitals.spo2_pct is not None and vitals.spo2_pct < 90,
    },
    {
        "name": "High Fever",
        "severity": "orange",
        "advice": "Temperature above 39°C. Administer antipyretic and monitor.",
        "condition": lambda symptoms, vitals: vitals and vitals.temperature_c is not None and vitals.temperature_c > 39.0,
    },
    {
        "name": "Very Low SpO2",
        "severity": "red",
        "advice": "CRITICAL: SpO2 below 85%. Emergency referral.",
        "condition": lambda symptoms, vitals: vitals and vitals.spo2_pct is not None and vitals.spo2_pct < 85,
    },
    {
        "name": "Hypertensive Crisis",
        "severity": "red",
        "advice": "URGENT: BP > 180/120. Hypertensive crisis. Refer immediately.",
        "condition": lambda symptoms, vitals: vitals and vitals.bp_systolic is not None and vitals.bp_systolic > 180,
    },
    {
        "name": "Bradycardia",
        "severity": "orange",
        "advice": "Pulse < 50 bpm. Check for cardiac issues.",
        "condition": lambda symptoms, vitals: vitals and vitals.pulse_bpm is not None and vitals.pulse_bpm < 50,
    },
    {
        "name": "Tachycardia",
        "severity": "orange",
        "advice": "Pulse > 120 bpm. Assess for underlying cause.",
        "condition": lambda symptoms, vitals: vitals and vitals.pulse_bpm is not None and vitals.pulse_bpm > 120,
    },
    {
        "name": "Chest Pain Symptom",
        "severity": "red",
        "advice": "URGENT: Chest pain reported. Consider cardiac emergency.",
        "condition": lambda symptoms, vitals: symptoms.get("chest_pain") is True,
    },
    {
        "name": "Loss of Consciousness",
        "severity": "red",
        "advice": "CRITICAL: Loss of consciousness reported. Emergency referral.",
        "condition": lambda symptoms, vitals: symptoms.get("loss_of_consciousness") is True,
    },
    {
        "name": "Severe Headache + Vomiting",
        "severity": "orange",
        "advice": "Possible raised ICP. Refer for evaluation.",
        "condition": lambda symptoms, vitals: symptoms.get("severe_headache") and symptoms.get("vomiting"),
    },
    {
        "name": "Difficulty Breathing",
        "severity": "red",
        "advice": "URGENT: Respiratory distress. Assess and refer if needed.",
        "condition": lambda symptoms, vitals: symptoms.get("difficulty_breathing") is True,
    },
]


@router.post(
    "/evaluate",
    response_model=TriageEvalResponse,
    summary="Evaluate symptoms and vitals for red-flag conditions",
    description=(
        "**IMPORTANT**: This output is labelled 'advice only' and must NOT be used as a "
        "diagnosis. A registered medical practitioner must confirm all clinical decisions."
    ),
)
async def evaluate_triage(
    body: TriageEvalRequest,
    current_user: CHWOrAbove,
):
    """
    Evaluate symptoms and vitals against built-in red-flag rules.
    Returns a list of triggered flags with severity and advice.
    """
    return run_triage(body.symptoms, body.vitals)


def run_triage(symptoms: dict | None, vitals: VitalsSchema | None) -> TriageEvalResponse:
    """Pure rule evaluation — also used to auto-flag encounters on save."""
    flags: list[TriageFlag] = []
    symptoms = symptoms or {}

    for rule in BUILT_IN_RULES:
        try:
            if rule["condition"](symptoms, vitals):
                flags.append(TriageFlag(
                    rule_name=rule["name"],
                    severity=rule["severity"],
                    advice=rule["advice"],
                ))
        except Exception:
            pass  # Never crash on triage rule evaluation

    # Deduplicate and sort by severity
    severity_order = {"red": 0, "orange": 1, "yellow": 2}
    flags.sort(key=lambda f: severity_order.get(f.severity, 3))

    urgent = any(f.severity == "red" for f in flags)

    if not flags:
        summary = "No immediate red flags detected. Continue routine assessment."
    elif urgent:
        summary = f"⚠️ URGENT: {len([f for f in flags if f.severity == 'red'])} critical flag(s). Consider emergency referral."
    else:
        summary = f"{len(flags)} flag(s) detected. Monitor and consult doctor."

    return TriageEvalResponse(
        flags=flags,
        urgent=urgent,
        summary=f"[ADVICE ONLY – not a diagnosis] {summary}",
    )


@router.get("/rules")
async def list_triage_rules(
    current_user: CHWOrAbove,
    db: AsyncSession = Depends(get_db),
):
    """List all active triage rules from database."""
    result = await db.execute(
        select(TriageRule).where(TriageRule.is_active.is_(True))
    )
    rules = result.scalars().all()
    return {
        "built_in_count": len(BUILT_IN_RULES),
        "db_rules": [{"id": str(r.id), "name": r.name, "severity": r.severity} for r in rules],
    }
