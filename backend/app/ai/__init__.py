"""AI Analyzer package — mock provider by default; never executes remediations."""

from app.ai.provider import AIProvider, MockAIProvider, get_ai_provider

__all__ = ["AIProvider", "MockAIProvider", "get_ai_provider"]
