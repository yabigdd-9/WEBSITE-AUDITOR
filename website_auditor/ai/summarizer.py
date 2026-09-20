import json, subprocess, urllib.request, urllib.error

class AISummarizer:
    """Generates plain-English summaries. Uses Ollama if available, else templates."""

    OLLAMA_URL = "http://localhost:11434/api/generate"

    def __init__(self, model="llama3.2"):
        self.model = model

    def is_ollama_running(self):
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    def summarize_with_ai(self, domain, defects, score):
        """Use local Ollama for natural language summary."""
        defect_list = "\n".join([
            f"- {d.get('issue', d.get('defect_key', str(d)))}" for d in defects[:5]
        ])

        prompt = f"""You are a website consultant for NZ small businesses. 
Summarize these audit findings in 2-3 plain English sentences for a non-technical business owner. 
Be helpful, not alarming. Mention the business impact.

Website: {domain}
Score: {score}/100
Issues found:
{defect_list}

Write a brief, friendly summary:"""

        payload = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }).encode()

        req = urllib.request.Request(
            self.OLLAMA_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                return data.get("response", "").strip()
        except Exception as e:
            return None

    def summarize_with_template(self, domain, defects, score):
        """Fallback: template-based summary without AI."""
        critical = [d for d in defects if "ssl" in str(d).lower() or "security" in str(d).lower()]
        seo = [d for d in defects if any(k in str(d).lower() for k in ["title", "meta", "h1", "seo"])]
        other = len(defects) - len(critical) - len(seo)

        summary = f"Your website ({domain}) scored {score}/100. "

        if critical:
            summary += f"There are {len(critical)} security item(s) that need attention soon — these affect visitor trust. "
        if seo:
            summary += f"There are {len(seo)} SEO improvement(s) that could help you appear higher in search results. "
        if other > 0:
            summary += f"Plus {other} other minor item(s). "

        if score >= 70:
            summary += "Overall your site is in decent shape — addressing the top items will make a real difference."
        elif score >= 40:
            summary += "Your site has solid foundations but needs some attention to perform at its best."
        else:
            summary += "There are several quick wins available that would significantly improve your site."

        return summary

    def generate_summary(self, domain, defects, score):
        """Main entry: try AI first, fall back to template."""
        if self.is_ollama_running():
            ai_summary = self.summarize_with_ai(domain, defects, score)
            if ai_summary:
                return {"summary": ai_summary, "source": "ollama_local_ai"}

        template_summary = self.summarize_with_template(domain, defects, score)
        return {"summary": template_summary, "source": "template_fallback"}
