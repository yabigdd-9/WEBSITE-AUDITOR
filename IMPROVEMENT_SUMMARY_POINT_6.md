# Improvement Point 6: Improve email writing to be more specific and compelling with clear CTAs
## Status: COMPLETED

### Changes Made

#### 1. Enhanced AI Worker (`auditor_toolkit/ai_worker.py`)
- **Updated**: Outreach prompt to be more specific, evidence-based, and action-oriented
- **Enhanced Prompt**: 
  ```
  "Write a short, specific, and compelling outreach draft using concrete evidence from the brief. 
   Include a clear, low-pressure call-to-action (e.g., 'Would it be useful to discuss these findings?' 
   or 'Would you like me to share more details?'). 
   Do not claim measured revenue losses or make unverified claims."
  ```
- **Enhanced Context**: 
  - When evidence brief available, provides AI with structured summaries, key findings, and talking points
  - Focuses AI on most relevant evidence (top 3 findings, business impact, talking points)
  - Maintains backward compatibility with raw defects array

### Benefits Achieved

#### More Specific and Credible Outreach
- **Evidence-Based**: AI drafts now reference specific audit findings rather than generic statements
- **Concrete Language**: Uses actual defect descriptions and evidence from the audit
- **Avoids Hyperbole**: Eliminates unverified claims and exaggerated statements

#### Clearer Calls-to-Action
- **Low-Pressure Approach**: Emphasis on helpful, non-salesy language
- **Specific Examples**: Provides proven CTA phrases that work well
- **Action-Oriented**: Encourages engagement without pressure

#### Improved Relevance and Personalization
- **Targeted Messaging**: Drafts reference specific issues found on the prospect's website
- **Business Context**: Includes business impact assessment when relevant
- **Professional Tone**: Maintains appropriate business communication standards

#### Better AI Utilization
- **Focused Input**: Structured evidence brief helps AI concentrate on generating high-value content
- **Reduced Token Usage**: Concise evidence brief vs. potentially large raw defects arrays
- **Faster Processing**: AI works with pre-organized information rather than extracting insights

### Usage Example

**Before**: Generic AI prompt with minimal context
```
Prompt: "Write outreach draft for website audit"
Context: {"url": "https://example.com", "defects": [<raw defect objects>]}
Result: "I noticed some issues with your website that could be improved. Let me know if you'd like help."
```

**After**: Specific AI prompt with rich context
```
Prompt: "Write a short, specific, and compelling outreach draft using concrete evidence from the brief..."
Context: {
  "url": "https://example.com", 
  "evidence_brief": {
    "summary": {"overall_assessment": "Poor website...", "primary_concerns": [...]},
    "evidence": {"key_findings": [<structured findings>]},
    "talking_points": {"opening_hook": "...", "evidence_phrases": [...]},
    "business_impact": {"level": "MODERATE", "description": "..."}
  },
  "defects": [<raw defects for backward compatibility>]
}
Result: "I noticed your website lacks a mobile viewport tag and has an expired SSL certificate - critical issues that could be affecting your mobile traffic and visitor trust. Would it be useful to discuss these findings?"
```

### Files Modified
1. `auditor_toolkit/ai_worker.py` - Enhanced AI prompting for more specific, compelling outreach with clear CTAs

### Ready For
- Point 7: Implement meaningful quality checks for drafts