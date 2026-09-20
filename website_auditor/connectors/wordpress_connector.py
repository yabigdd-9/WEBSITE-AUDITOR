import json
import subprocess
from pathlib import Path
from urllib.parse import urlparse
import urllib.request
import urllib.error


class WordPressConnector:
    """Detects WordPress sites and generates remediation instructions.
    
    Does not modify live sites — generates actionable fix instructions
    specific to WordPress (theme editor, REST API, plugin recommendations).
    """
    
    def detect_cms(self, domain: str) -> dict:
        """Detect if a domain is WordPress and return CMS info."""
        info = {
            "domain": domain,
            "cms": "unknown",
            "is_wordpress": False,
            "wp_version": None,
            "theme": None,
            "plugins": [],
            "detection_method": None,
        }
        
        try:
            # Check common WP indicators
            urls_to_check = [
                f"https://{domain}/wp-login.php",
                f"https://{domain}/wp-admin/",
                f"https://{domain}/readme.html",
                f"https://{domain}/wp-content/",
            ]
            
            for url in urls_to_check:
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "WebsiteAuditor/1.0"})
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        if resp.status == 200:
                            path = urlparse(url).path
                            if "/wp-login.php" in path or "/wp-admin/" in path:
                                info["is_wordpress"] = True
                                info["cms"] = "WordPress"
                                info["detection_method"] = f"HTTP 200 on {path}"
                                break
                except Exception:
                    continue
            
            # Check generator tag via main page
            if not info["is_wordpress"]:
                try:
                    req = urllib.request.Request(
                        f"https://{domain}/",
                        headers={"User-Agent": "WebsiteAuditor/1.0"}
                    )
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        html = resp.read().decode("utf-8", errors="ignore")
                        if "wp-content" in html or "wordpress" in html.lower():
                            info["is_wordpress"] = True
                            info["cms"] = "WordPress"
                            info["detection_method"] = "HTML content check"
                except Exception:
                    pass
                    
        except Exception as e:
            info["error"] = str(e)
        
        return info
    
    def generate_wordpress_fix_instructions(self, action, cms_info: dict) -> dict:
        """Generate WordPress-specific fix instructions for an action."""
        domain = action.domain
        action_id = action.action_id
        defect = action.payload.get("defect", {})
        
        instructions = {
            "domain": domain,
            "action_id": action_id,
            "cms": cms_info.get("cms", "unknown"),
            "is_wordpress": cms_info.get("is_wordpress", False),
            "instructions": [],
            "plugin_suggestions": [],
            "theme_file_paths": [],
            "rest_api_endpoints": [],
            " difficulty": "easy",
        }
        
        if not cms_info.get("is_wordpress"):
            instructions["instructions"].append(
                f"Site does not appear to be WordPress. Manual review required for: {action.name}"
            )
            return instructions
        
        # Map action IDs to WordPress-specific fixes
        fix_map = {
            "headers.add_hsts_propose": {
                "instructions": [
                    "Add to wp-config.php: define('FORCE_SSL_ADMIN', true);",
                    "Add HSTS header via security plugin (Wordfence, iThemes) or .htaccess:",
                    "  Header always set Strict-Transport-Security 'max-age=31536000; includeSubDomains'",
                    "Or add via theme functions.php using header() call.",
                ],
                "plugin_suggestions": ["Wordfence", "iThemes Security", "Really Simple SSL"],
                "theme_file_paths": ["wp-content/themes/{theme}/functions.php"],
                "difficulty": "medium",
            },
            "content.add_meta_description_patch": {
                "instructions": [
                    "Via SEO plugin (Yoast, RankMath, All in One SEO):",
                    "  1. Edit the page/post in WordPress admin",
                    "  2. Scroll to SEO meta box",
                    "  3. Add meta description (150-160 chars)",
                    "Or via theme: edit header.php or use add_action('wp_head', ...) in functions.php.",
                ],
                "plugin_suggestions": ["Yoast SEO", "RankMath", "All in One SEO"],
                "difficulty": "easy",
            },
            "review.defect": {
                "instructions": [
                    "Create a task in your project management tool.",
                    "Assign to developer/theme editor.",
                    "Reference: " + action.payload.get("details", {}).get("issue", "See defect data"),
                ],
                "difficulty": "easy",
            },
        }
        
        # Default fallback
        default_fix = {
            "instructions": [
                f"Review and fix: {action.name}",
                "Via WordPress admin: edit the relevant page/post/theme file.",
                "Or via FTP/SFTP: edit wp-content/themes/{theme}/ files.",
                "Test on staging first before deploying to production.",
            ],
            "difficulty": "medium",
        }
        
        fix = fix_map.get(action_id, default_fix)
        instructions["instructions"] = fix["instructions"]
        instructions["plugin_suggestions"] = fix.get("plugin_suggestions", [])
        instructions["theme_file_paths"] = fix.get("theme_file_paths", [])
        instructions["difficulty"] = fix.get("difficulty", "medium")
        
        # Add REST API endpoints if relevant
        if "meta" in action_id or "title" in action_id:
            instructions["rest_api_endpoints"] = [
                f"GET https://{domain}/wp-json/wp/v2/pages?search={domain}",
                f"GET https://{domain}/wp-json/wp/v2/posts?search={domain}",
            ]
        
        return instructions
    
    def execute_wordpress_fix(self, action):
        """Generate WordPress fix instructions and save locally.
        
        Does NOT modify live WordPress sites.
        """
        domain = action.domain
        
        try:
            cms_info = self.detect_cms(domain)
        except Exception as e:
            cms_info = {"cms": "unknown", "is_wordpress": False, "error": str(e)}
        
        instructions = self.generate_wordpress_fix_instructions(action, cms_info)
        
        # Save instructions to outputs
        output_dir = Path(f"outputs/wp-fixes/{domain}")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / f"{action.action_id}.json"
        output_file.write_text(json.dumps(instructions, indent=2))
        
        result = {
            "status": "instructions_generated",
            "action_id": action.action_id,
            "domain": domain,
            "cms": cms_info.get("cms"),
            "is_wordpress": cms_info.get("is_wordpress"),
            "output_file": str(output_file),
            "instructions_count": len(instructions.get("instructions", [])),
            "plugin_suggestions": instructions.get("plugin_suggestions", []),
            "difficulty": instructions.get("difficulty"),
        }
        
        return result
