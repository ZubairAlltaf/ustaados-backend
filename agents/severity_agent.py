"""
UstaadOS — Severity Agent
Estimates issue severity, technical complexity, expected repair duration,
and likely parts needed. Feeds into Matching and Pricing agents.
"""
import json
import re
from agents.base_agent import BaseAgent


class SeverityAgent(BaseAgent):
    name = "SeverityAgent"

    SEVERITY_MAP = {
        "AC Repair": {
            "Gas Leakage": {"score": 4.2, "duration": 90, "complexity": "high"},
            "Compressor Issue": {"score": 4.5, "duration": 120, "complexity": "high"},
            "Cooling Failure": {"score": 3.8, "duration": 75, "complexity": "medium"},
            "Remote Not Working": {"score": 1.5, "duration": 20, "complexity": "low"},
            "Water Leakage": {"score": 2.8, "duration": 45, "complexity": "medium"},
            "Noise Problem": {"score": 2.5, "duration": 40, "complexity": "medium"},
            "Not Turning On": {"score": 3.5, "duration": 60, "complexity": "medium"},
            "Electrical Fault": {"score": 4.0, "duration": 90, "complexity": "high"},
        },
        "Solar Inverter Repair": {
            "Inverter Failure": {"score": 4.8, "duration": 120, "complexity": "critical"},
            "Battery Not Charging": {"score": 4.0, "duration": 90, "complexity": "high"},
            "Output Power Low": {"score": 3.5, "duration": 75, "complexity": "medium"},
            "Display Error": {"score": 2.0, "duration": 30, "complexity": "low"},
            "Overheating": {"score": 4.2, "duration": 60, "complexity": "high"},
            "No Output": {"score": 4.9, "duration": 90, "complexity": "critical"},
            "Load Shedding Issue": {"score": 4.7, "duration": 90, "complexity": "critical"},
        },
        "Refrigerator Repair": {
            "Not Cooling": {"score": 4.0, "duration": 90, "complexity": "high"},
            "Compressor Noise": {"score": 3.5, "duration": 60, "complexity": "medium"},
            "Ice Maker Issue": {"score": 2.5, "duration": 45, "complexity": "medium"},
            "Door Seal Damaged": {"score": 1.8, "duration": 30, "complexity": "low"},
            "Temperature Fluctuation": {"score": 3.2, "duration": 60, "complexity": "medium"},
            "Electrical Fault": {"score": 4.0, "duration": 75, "complexity": "high"},
        },
        "Washing Machine Repair": {
            "Not Spinning": {"score": 3.5, "duration": 60, "complexity": "medium"},
            "Drainage Issue": {"score": 3.0, "duration": 45, "complexity": "medium"},
            "Noise Problem": {"score": 2.5, "duration": 40, "complexity": "medium"},
            "Not Starting": {"score": 3.8, "duration": 60, "complexity": "high"},
            "Water Leakage": {"score": 3.2, "duration": 50, "complexity": "medium"},
        },
        "HVAC Installation": {
            "New Installation": {"score": 3.0, "duration": 240, "complexity": "high"},
            "System Upgrade": {"score": 2.5, "duration": 180, "complexity": "medium"},
            "Multi-Zone Setup": {"score": 4.0, "duration": 360, "complexity": "critical"},
        },
    }

    LIKELY_PARTS = {
        "Gas Leakage": ["Refrigerant (R410A)", "Leak Detection Kit"],
        "Compressor Issue": ["Compressor", "Capacitor", "Relay"],
        "Inverter Failure": ["Inverter Board", "Power Module"],
        "Battery Not Charging": ["Battery Cells", "Charge Controller"],
        "Not Cooling": ["Thermostat", "Refrigerant", "Evaporator"],
        "Electrical Fault": ["PCB Board", "Fuse", "Wiring"],
    }

    def observe(self, inputs: dict) -> dict:
        intent = inputs.get("intent", {})
        weather_temp = inputs.get("weather_temp", 35.0)

        service = intent.get("service_type", "AC Repair")
        issue = intent.get("issue_description", "General Repair")
        urgency = intent.get("urgency_level", "medium")

        # Match to known issue
        service_issues = self.SEVERITY_MAP.get(service, {})
        matched_issue = None
        for known_issue in service_issues:
            if known_issue.lower() in issue.lower() or issue.lower() in known_issue.lower():
                matched_issue = known_issue
                break

        return {
            "service": service,
            "issue": issue,
            "matched_issue": matched_issue,
            "urgency": urgency,
            "weather_temp": weather_temp,
            "is_heatwave": weather_temp > 40,
            "summary": f"Analyzing {service} | Issue: {issue} | Temp: {weather_temp}°C",
        }

    def reason(self, observation: dict) -> str:
        service = observation["service"]
        issue = observation["issue"]
        matched = observation["matched_issue"]
        urgency = observation["urgency"]
        temp = observation["weather_temp"]

        # Use lookup table first
        if matched:
            data = self.SEVERITY_MAP[service].get(matched, {})
            score = data.get("score", 2.5)
            duration = data.get("duration", 60)
            complexity = data.get("complexity", "medium")
            parts = self.LIKELY_PARTS.get(matched, ["Standard parts"])

            # Heatwave escalation
            if temp > 40 and service in ["AC Repair", "Solar Inverter Repair", "HVAC Installation"]:
                score = min(5.0, score + 0.5)
                complexity = "critical" if complexity == "high" else complexity

            return json.dumps({
                "severity_score": score,
                "complexity": complexity,
                "estimated_duration_minutes": duration,
                "likely_parts": parts,
                "risk_level": "critical" if score >= 4.5 else "high" if score >= 3.5 else "medium" if score >= 2.5 else "low",
                "heatwave_escalated": temp > 40,
                "reasoning": f"Issue '{matched}' for {service} has known severity {score}/5. "
                             f"Heatwave escalation: {temp > 40}.",
            })

        # Fallback to LLM for unknown issues
        prompt = f"""You are a Pakistani appliance technician expert.

Analyze this service request and return ONLY valid JSON:

Service: {service}
Issue: {issue}
Urgency: {urgency}
Weather Temperature: {temp}°C

Return JSON with:
- severity_score: float 1.0-5.0 (5 = critical emergency)
- complexity: low/medium/high/critical
- estimated_duration_minutes: int
- likely_parts: list of parts likely needed
- risk_level: low/medium/high/critical
- heatwave_escalated: true/false (if temp > 40 affects severity)
- reasoning: brief explanation

JSON only, no markdown."""
        return self.call_llm(prompt, temperature=0.1)

    def decide(self, reasoning: str) -> dict:
        try:
            clean = re.sub(r"```json\s*|\s*```", "", reasoning).strip()
            parsed = json.loads(clean)
            return {
                "severity_score": float(parsed.get("severity_score", 2.5)),
                "complexity": parsed.get("complexity", "medium"),
                "estimated_duration_minutes": int(parsed.get("estimated_duration_minutes", 60)),
                "likely_parts": parsed.get("likely_parts", []),
                "risk_level": parsed.get("risk_level", "medium"),
                "heatwave_escalated": parsed.get("heatwave_escalated", False),
                "reasoning_text": parsed.get("reasoning", ""),
                "confidence": 0.9,
                "summary": f"Severity: {parsed.get('severity_score', 2.5)}/5 | "
                           f"Complexity: {parsed.get('complexity')} | "
                           f"ETA: {parsed.get('estimated_duration_minutes')} min",
            }
        except Exception:
            return {
                "severity_score": 2.5,
                "complexity": "medium",
                "estimated_duration_minutes": 60,
                "likely_parts": [],
                "risk_level": "medium",
                "heatwave_escalated": False,
                "reasoning_text": "Defaulted due to parse error",
                "confidence": 0.4,
                "summary": "Severity: 2.5/5 | Complexity: medium (default)",
            }

    def act(self, decision: dict) -> dict:
        risk = decision["risk_level"]
        if risk == "critical":
            action = "Escalated to CRITICAL priority. Prioritizing nearest available expert technician."
        elif risk == "high":
            action = "Flagged as HIGH severity. Routing to experienced technicians only."
        else:
            action = f"Severity classified as {risk}. Standard routing applied."

        return {
            "action_taken": action,
            "result": f"Severity score: {decision['severity_score']}/5 | "
                      f"Est. duration: {decision['estimated_duration_minutes']} min | "
                      f"Risk: {decision['risk_level']}",
            "output": decision,
        }
