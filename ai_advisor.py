def analyze_pages(rows):
    recommendations = []

    for page in rows:
        url = page.get("page", "")
        status = page.get("http_status")

        if not isinstance(status, int) or status >= 400:
            recommendations.append({
                "page": url,
                "problem": "Page unavailable or scan failed",
                "solution": "Check the URL, server and HTTP response.",
                "reason": "Search engines and visitors may be unable to access this page.",
                "risk": "Low risk to investigate. Server or URL changes should be reviewed before applying them.",
                "priority": "High",
                "autofix": False
            })
            continue

        if not page.get("title"):
            recommendations.append({
                "page": url,
                "problem": "Missing SEO title",
                "solution": "Add a unique, descriptive page title.",
                "reason": "A clear SEO title helps search engines and visitors understand the page.",
                "risk": "Low to medium: changing a title can affect how the page appears in search results.",
                "priority": "High",
                "autofix": False
            })

        if not page.get("meta_description"):
            recommendations.append({
                "page": url,
                "problem": "Missing meta description",
                "solution": "Write a relevant description summarizing the page.",
                "reason": "A relevant description may help visitors understand the page in search results.",
                "risk": "Low: an inaccurate or generic description may mislead visitors or be ignored by search engines.",
                "priority": "Medium",
                "autofix": False
            })

        if page.get("h1_count") != 1:
            recommendations.append({
                "page": url,
                "problem": "H1 structure needs review",
                "solution": "Review the page's main heading structure.",
                "reason": "A clear main heading helps communicate the page topic and content hierarchy.",
                "risk": "Medium: editing headings may change the page layout or content hierarchy.",
                "priority": "Medium",
                "autofix": False
            })

        if page.get("images_missing_alt", 0) > 0:
            recommendations.append({
                "page": url,
                "problem": "Images missing ALT text",
                "solution": "Add meaningful ALT text to informative images.",
                "reason": "Descriptive alternative text improves accessibility and provides image context.",
                "risk": "Low: inaccurate ALT text can confuse screen-reader users; decorative images may need empty ALT text.",
                "priority": "Medium",
                "autofix": False
            })

    return recommendations


def suggest_meta_description(title):
    if not title:
        return "Add a clear page title first."

    return (
        f"Discover {title}. Learn more about "
        "our services, benefits, and solutions."
    )
