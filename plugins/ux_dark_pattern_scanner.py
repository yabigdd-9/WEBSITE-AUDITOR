from bs4 import BeautifulSoup
import re

def scan_dark_patterns(html_content):
    issues = []
    soup = BeautifulSoup(html_content, 'html.parser')
    text_content = soup.get_text().lower()
    
    shaming_keywords = ['no thanks, i', 'no, i prefer', 'i will pay full price', 'i hate saving']
    for phrase in shaming_keywords:
        if phrase in text_content:
            issues.append({"type": "Confirmshaming", "severity": "High", "description": f"Found manipulative decline text: '{phrase}'"})
            break
            
    checkboxes = soup.find_all('input', {'type': 'checkbox'})
    for box in checkboxes:
        if box.has_attr('checked'):
            issues.append({"type": "Pre-ticked Consent", "severity": "High", "description": "Found a checkbox that is checked by default."})
            break

    return issues
