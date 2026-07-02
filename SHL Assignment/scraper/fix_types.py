"""
Post-process the catalog to fix test_type for items scraped from detail pages.
Infer type from name, description, and URL patterns.
"""
import json
import re

INPUT_PATH = "data/catalog.json"

# Test type codes:
# A = Ability (general cognitive)
# B = Behavioral/SJT
# C = Competency
# D = Development
# E = Experience/Simulation
# K = Knowledge
# P = Personality
# S = Skills/Simulation

# Rules for inferring test_type from name/description
TYPE_RULES = [
    # Personality tests
    (r"(?i)(OPQ|personality|motivation questionnaire|MQ\b|temperament)", "P"),
    # Cognitive/Ability tests  
    (r"(?i)(verify|numerical reasoning|verbal reasoning|inductive|deductive|cognitive|ability test|checking|g\+|general ability)", "A"),
    # Behavioral/SJT tests
    (r"(?i)(scenarios|situational|SJT|behavioral|judgement|judgment|workplace safety|dependability)", "B"),
    # Competency frameworks
    (r"(?i)(competency|UCF|360|multi.?rater|leadership report|development report)", "C"),
    # Simulations
    (r"(?i)(simulation|automata|coding sim|call center sim|data entry sim|interactive)", "E"),
    # Knowledge tests (most specific patterns last as this is the default for tech tests)
    (r"(?i)(\.NET|java|python|javascript|C\#|SQL|HTML|CSS|PHP|angular|react|node\.?js|ruby|rails|spring|docker|kubernetes|aws|azure|linux|agile|devops|hadoop|spark|kafka|selenium|drupal|wordpress|salesforce|SAP|tableau|power ?BI|machine learning|data science|cybersecurity|networking|mechanical|electrical|accounting|marketing|project management|HR |human resources|supply chain|quality management|R programming)", "K"),
    (r"(?i)(new\)|knowledge|multi.?choice test that measures the knowledge)", "K"),
    # Skills
    (r"(?i)(typing|speed|accuracy|language evaluation|SVAR|spoken|english comprehension|business english)", "S"),
]


def infer_test_type(item: dict) -> str:
    """Infer test_type from item name and description."""
    name = item.get("name", "")
    desc = item.get("description", "")
    combined = f"{name} {desc}"

    for pattern, type_code in TYPE_RULES:
        if re.search(pattern, combined):
            return type_code

    # Default: if description mentions "multi-choice test that measures the knowledge"
    if "multi-choice" in desc.lower() or "knowledge" in desc.lower():
        return "K"

    # If name has "(New)" it's likely a knowledge test
    if "(New)" in name or "(new)" in name:
        return "K"

    return "K"  # Default to Knowledge for unclassified items


def fix_catalog():
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    fixed_count = 0
    for item in catalog:
        test_type = item.get("test_type", "")
        
        # Fix items that have wrong test_type (from detail page scraping)
        if not test_type or "Remote Testing" in test_type or len(test_type) > 10:
            item["test_type"] = infer_test_type(item)
            fixed_count += 1

        # Also fix remote_testing field
        if item.get("test_type_raw"):
            del item["test_type_raw"]

        # Ensure URL is clean (no wayback prefix)
        url = item.get("url", "")
        if "/web/" in url:
            match = re.search(r"(https://www\.shl\.com/.*)", url)
            if match:
                item["url"] = match.group(1)

    with open(INPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

    print(f"Fixed test_type for {fixed_count}/{len(catalog)} items")
    
    # Print type distribution
    types = {}
    for item in catalog:
        tt = item.get("test_type", "?")
        types[tt] = types.get(tt, 0) + 1
    print(f"Type distribution: {json.dumps(types, indent=2)}")


if __name__ == "__main__":
    fix_catalog()
