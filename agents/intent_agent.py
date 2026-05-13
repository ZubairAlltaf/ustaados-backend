"""
UstaadOS — Intent Agent
Understands multilingual (Roman Urdu / Urdu / English) user requests
and extracts structured intent for downstream agents.
"""
import json
import re
from agents.base_agent import BaseAgent


class IntentAgent(BaseAgent):
    name = "IntentAgent"

    SYSTEM_PROMPT = """You are UstaadOS's Intent Agent.
Your job is to understand service requests written in Roman Urdu, Urdu, or English.
Extract structured information and return ONLY valid JSON.

Extract these fields:
- service_type: one of [AC Repair, Refrigerator Repair, Washing Machine Repair, Solar Inverter Repair, HVAC Installation]
- issue_description: brief English description of the problem
- urgency_level: one of [low, medium, high, critical]
- urgency_reason: why you assigned this urgency
- time_preference: when the user wants service (e.g., "Tomorrow Morning", "Today Evening", "ASAP", "Any")
- location_hint: any area/location mentioned
- budget_hint: any price/budget mentioned (null if not mentioned)
- language_detected: one of [roman_urdu, urdu, english, mixed]
- confidence: float 0.0-1.0 (how confident you are in the extraction)
- needs_clarification: true/false
- clarification_question: question to ask if needs_clarification is true (in same language as input)

Urgency rules:
- critical: no electricity backup, safety hazard, heatwave, complete failure of essential system
- high: not cooling/heating at all, major malfunction
- medium: partial issue, reduced performance
- low: minor issue, maintenance request

Roman Urdu examples:
"AC band ho gaya" → AC Repair, high urgency
"Solar inverter band ho gaya, load shedding mein backup nahi" → Solar Inverter Repair, critical urgency
"Fridge thanda nahi kar raha" → Refrigerator Repair, high urgency
"Washing machine se awaaz aa rahi hai" → Washing Machine Repair, medium urgency

Return ONLY valid JSON, no markdown, no explanation."""

    def observe(self, inputs: dict) -> dict:
        text = inputs.get("text", "")
        voice_transcript = inputs.get("voice_transcript", "")
        user_location = inputs.get("location", {})

        raw_input = voice_transcript if voice_transcript else text

        return {
            "raw_input": raw_input,
            "has_voice": bool(voice_transcript),
            "user_location": user_location,
            "input_length": len(raw_input),
            "summary": f"Received request: '{raw_input[:100]}...' " if len(raw_input) > 100 else f"Received request: '{raw_input}'",
        }

    def reason(self, observation: dict) -> str:
        raw_input = observation["raw_input"]
        prompt = f"""{self.SYSTEM_PROMPT}

User request: "{raw_input}"

Return JSON only:"""
        return self.call_llm(prompt, temperature=0.1)

    def decide(self, reasoning: str) -> dict:
        """Parse LLM JSON output into a structured decision."""
        try:
            # Strip markdown if present
            clean = re.sub(r"```json\s*|\s*```", "", reasoning).strip()
            parsed = json.loads(clean)

            return {
                "service_type": parsed.get("service_type", "AC Repair"),
                "issue_description": parsed.get("issue_description", "General service request"),
                "urgency_level": parsed.get("urgency_level", "medium"),
                "urgency_reason": parsed.get("urgency_reason", ""),
                "time_preference": parsed.get("time_preference", "Any"),
                "location_hint": parsed.get("location_hint", ""),
                "budget_hint": parsed.get("budget_hint"),
                "language_detected": parsed.get("language_detected", "roman_urdu"),
                "confidence": float(parsed.get("confidence", 0.8)),
                "needs_clarification": parsed.get("needs_clarification", False),
                "clarification_question": parsed.get("clarification_question", ""),
                "summary": f"{parsed.get('service_type')} | {parsed.get('urgency_level')} urgency | confidence: {parsed.get('confidence', 0.8):.0%}",
                "raw_parsed": parsed,
            }
        except (json.JSONDecodeError, ValueError) as e:
            # Fallback for LLM parse failure
            return {
                "service_type": "AC Repair",
                "issue_description": "Could not parse request",
                "urgency_level": "medium",
                "urgency_reason": "Defaulted due to parse error",
                "time_preference": "Any",
                "location_hint": "",
                "budget_hint": None,
                "language_detected": "unknown",
                "confidence": 0.3,
                "needs_clarification": True,
                "clarification_question": "Maazrat, mujhe theek se samajh nahi aayi. Kya aap tafseel se masla bata sakte hain?",
                "summary": f"Parse failed ({str(e)[:50]}). Clarification needed.",
                "raw_parsed": {},
            }

    def act(self, decision: dict) -> dict:
        """Pass the structured intent downstream."""
        if decision["needs_clarification"]:
            action = f"Sent clarification request to user: '{decision['clarification_question']}'"
        else:
            action = f"Intent extracted. Routing to Severity Agent: {decision['service_type']}"

        return {
            "action_taken": action,
            "result": f"Structured intent ready. Service: {decision['service_type']}, "
                      f"Urgency: {decision['urgency_level']}, "
                      f"Confidence: {decision['confidence']:.0%}",
            "output": decision,
        }
