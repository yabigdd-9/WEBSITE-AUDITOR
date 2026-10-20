import re
from bs4 import BeautifulSoup

def detect_tech_stack(html_content, headers):
    tech_stack = []
    server = headers.get('Server', '').lower()
    if 'nginx' in server: tech_stack.append('Nginx')
    if 'apache' in server: tech_stack.append('Apache')
    if 'cloudflare' in server: tech_stack.append('Cloudflare')
    
    powered_by = headers.get('X-Powered-By', '').lower()
    if 'php' in powered_by: tech_stack.append('PHP')
    if 'asp.net' in powered_by: tech_stack.append('ASP.NET')
    if 'express' in powered_by: tech_stack.append('Express.js')
    
    soup = BeautifulSoup(html_content, 'html.parser')
    generator = soup.find('meta', attrs={'name': 'generator'})
    if generator and generator.get('content'):
        gen_content = generator['content'].lower()
        if 'wordpress' in gen_content: tech_stack.append('WordPress')
        if 'shopify' in gen_content: tech_stack.append('Shopify')
        if 'wix' in gen_content: tech_stack.append('Wix')
        if 'webflow' in gen_content: tech_stack.append('Webflow')
        
    scripts = [script.get('src', '') for script in soup.find_all('script') if script.get('src')]
    script_string = ' '.join(scripts).lower()
    if 'react' in script_string: tech_stack.append('React')
    if 'vue' in script_string: tech_stack.append('Vue.js')
    if 'angular' in script_string: tech_stack.append('Angular')
    if 'jquery' in script_string: tech_stack.append('jQuery')
        
    return list(set(tech_stack))
