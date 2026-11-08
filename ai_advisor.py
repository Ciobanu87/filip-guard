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
                "priority": "High",
                "autofix": False
            })
            continue

        if not page.get("title"):
            recommendations.append({
                "page": url,
                "problem": "Missing SEO title",
                "solution": "Add a unique, descriptive page title.",
                "priority": "High",
                "autofix": False
            })

        if not page.get("meta_description"):
            recommendations.append({
                "page": url,
                "problem": "Missing meta description",
                "solution": "Write a relevant description summarizing the page.",
                "priority": "Medium",
                "autofix": False
            })

        if page.get("h1_count") != 1:
            recommendations.append({
                "page": url,
                "problem": "H1 structure needs review",
                "solution": "Review the page's main heading structure.",
                "priority": "Medium",
                "autofix": False
            })

        if page.get("images_missing_alt", 0) > 0:
            recommendations.append({
                "page": url,
                "problem": "Images missing ALT text",
                "solution": "Add meaningful ALT text to informative images.",
                "priority": "Medium",
                "autofix": False
            })

    return recommendations
