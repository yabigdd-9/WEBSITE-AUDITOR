"""AI upgrade: tone control + bilingual."""
TONES = {
    "professional": "Formal, data-driven, suitable for corporate clients",
    "friendly": "Warm, encouraging, suitable for small business owners",
    "urgent": "Direct, action-focused, for critical issues only",
    "te_reo": "Include te reo Māori greetings and sign-offs where appropriate",
}
PROMPT_TEMPLATE = """
Kia ora! You are a website consultant for NZ small businesses.
Tone: {tone}
Summarize these findings in 2-3 sentences for a non-technical owner.
Mention business impact. Be helpful, not alarming.

Website: {domain}
Score: {score}/100
Issues: {issues}
"""
print("✅ Tone control + te reo Māori option ready for Ollama integration.")
