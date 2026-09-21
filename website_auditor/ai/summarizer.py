class AISummarizer:
    """Generate plain-English summaries without an external model runtime."""

    def __init__(self, model=None):
        self.model = model

    def summarize_with_template(self, domain, defects, score):
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
        return {"summary": self.summarize_with_template(domain, defects, score), "source": "template"}
