"""
UstaadOS — Base Agent
All agents inherit from this class and produce Antigravity-format traces.
"""
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import google.generativeai as genai

from config import GEMINI_API_KEY
from database.client import get_db

genai.configure(api_key=GEMINI_API_KEY)


class BaseAgent(ABC):
    """
    Every UstaadOS agent follows the Antigravity trace format:
      observe → reason → decide → act → (recover)
    """

    name: str = "BaseAgent"
    model_name: str = "gemini-1.5-flash"

    def __init__(self, session_id: str | None = None, booking_id: str | None = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.booking_id = booking_id
        self._model = genai.GenerativeModel(self.model_name)
        self._trace: dict = {}
        self._start_time: float = 0.0

    # ─── Core Lifecycle ────────────────────────────────────────────────────

    @abstractmethod
    def observe(self, inputs: dict) -> dict:
        """Gather and structure all inputs for reasoning."""
        ...

    @abstractmethod
    def reason(self, observation: dict) -> str:
        """Call Gemini LLM to produce structured reasoning."""
        ...

    @abstractmethod
    def decide(self, reasoning: str) -> dict:
        """Parse reasoning into a structured decision dict."""
        ...

    @abstractmethod
    def act(self, decision: dict) -> dict:
        """Execute the decision and return outcome."""
        ...

    # ─── Main Entry Point ──────────────────────────────────────────────────

    def run(self, inputs: dict) -> dict:
        """
        Execute the full agent lifecycle and return a complete trace.
        Returns: {observation, reasoning, decision, action, outcome, trace_id}
        """
        self._start_time = time.time()

        observation = self.observe(inputs)
        reasoning = self.reason(observation)
        decision = self.decide(reasoning)
        outcome = self.act(decision)

        exec_ms = int((time.time() - self._start_time) * 1000)

        trace = {
            "id": str(uuid.uuid4()),
            "booking_id": self.booking_id,
            "session_id": self.session_id,
            "agent_name": self.name,
            "observation": observation.get("summary", str(observation)),
            "reasoning": reasoning,
            "decision": decision.get("summary", str(decision)),
            "action": outcome.get("action_taken", ""),
            "outcome": outcome.get("result", ""),
            "recovery": outcome.get("recovery", None),
            "confidence_score": decision.get("confidence", 0.0),
            "execution_time_ms": exec_ms,
            "metadata": {
                "observation_detail": observation,
                "decision_detail": decision,
                "outcome_detail": outcome,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

        self._trace = trace
        self._persist_trace(trace)
        return trace

    # ─── LLM Helpers ──────────────────────────────────────────────────────

    def call_llm(self, prompt: str, temperature: float = 0.2) -> str:
        """Call Gemini and return the text response."""
        try:
            response = self._model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=1024,
                ),
            )
            return response.text.strip()
        except Exception as e:
            return f"LLM_ERROR: {str(e)}"

    # ─── Persistence ──────────────────────────────────────────────────────

    def _persist_trace(self, trace: dict) -> None:
        """Store trace in Supabase traces table."""
        try:
            db = get_db()
            payload = {k: v for k, v in trace.items() if k != "metadata"}
            payload["metadata"] = trace.get("metadata", {})
            db.table("traces").insert(payload).execute()
        except Exception as e:
            # Non-fatal — traces are best-effort
            print(f"[{self.name}] Trace persist failed: {e}")

    # ─── Utilities ─────────────────────────────────────────────────────────

    def get_trace(self) -> dict:
        return self._trace

    def build_trace_summary(self, obs: str, reason: str, dec: str, act: str, out: str, rec: str = "") -> dict:
        """Helper to build a standardised trace dict for subclasses."""
        return {
            "observation": obs,
            "reasoning": reason,
            "decision": dec,
            "action_taken": act,
            "result": out,
            "recovery": rec or None,
        }
