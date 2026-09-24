"""Shared web components for auditor toolkit."""
from pathlib import Path

def generate_web_calculator_html() -> str:
    """Generates the interactive ROI calculator HTML/JS."""
    # (Content extracted from calculator.py's generate_web_calculator function)
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Website Rescue Calculator</title>
    <!-- ... (Calculator HTML/JS content) ... -->
</head>
<body>
    <!-- Calculator body -->
</body>
</html>"""

def save_web_calculator(path: str = "outputs/calculator.html"):
    """Saves the web calculator to a file."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(generate_web_calculator_html())