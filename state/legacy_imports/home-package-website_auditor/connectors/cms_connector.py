
import os, json, urllib.request, base64

class CMSConnector:
    def __init__(self):
        self.wp_url = os.getenv("WP_SITE_URL", "").rstrip("/")
        self.wp_user = os.getenv("WP_USERNAME", "")
        self.wp_pass = os.getenv("WP_APP_PASSWORD", "")

    def create_wordpress_draft(self, title, content):
        if not self.wp_url or not self.wp_user:
            return {"status": "skipped", "reason": "WP_SITE_URL or WP_USERNAME not set"}
        
        url = f"{self.wp_url}/wp-json/wp/v2/posts"
        payload = json.dumps({
            "title": title,
            "content": content,
            "status": "draft"
        }).encode()
        
        auth = base64.b64encode(f"{self.wp_user}:{self.wp_pass}".encode()).decode()
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Basic {auth}")
        
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
                return {"status": "success", "edit_url": data.get("link")}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def execute_action(self, action):
        # Generates a CMS draft based on the Action Engine's patch
        title = f"[Auto-Fix] {action.name} for {action.domain}"
        content = f"<h2>Proposed Fix</h2><p>{action.name}</p><pre>{json.dumps(action.payload, indent=2)}</pre>"
        return self.create_wordpress_draft(title, content)
