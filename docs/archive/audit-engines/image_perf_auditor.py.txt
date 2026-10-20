from bs4 import BeautifulSoup

def audit_image_performance(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    images = soup.find_all('img')
    if not images: return {"score": 100, "issues": []}
        
    missing_lazy = sum(1 for img in images if img.get('loading', '').lower() != 'lazy')
    missing_srcset = sum(1 for img in images if not img.has_attr('srcset') and img.parent.name != 'picture')
    legacy_formats = sum(1 for img in images if img.get('src', '').lower().endswith(('.png', '.jpg', '.jpeg')))

    return {"total_images": len(images), "missing_lazy_load": missing_lazy, "missing_responsive_srcset": missing_srcset, "legacy_formats_count": legacy_formats, "optimization_score": max(0, 100 - ((legacy_formats / len(images)) * 50))}
