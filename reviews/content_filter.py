"""Content filter for buyer reviews (SEC-29).

A review that trips the filter is saved but held: it is not shown on the book
page or counted in ratings until an administrator approves it in Django admin.
The filter is deliberately simple and errs on the side of holding a review.
"""

import re

# Abusive words and common spam phrases; extend as moderators see new patterns.
BLOCKED_TERMS = (
    "idiot", "stupid", "moron", "scam", "fraud", "fuck", "shit", "bitch", "bastard", "asshole",
    "buy followers", "free money", "click here", "whatsapp me", "casino", "crypto giveaway",
)
LINK = re.compile(r"(https?://|www\.)\S+", re.IGNORECASE)
MARKUP = re.compile(r"<\s*/?\s*[a-z][^>]*>", re.IGNORECASE)
CONTACT = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\+?\d[\d\s-]{8,}\d")


def reasons(text):
    """Why ``text`` should be held, or an empty list if it may be published."""
    text = text or ""
    lowered = text.lower()
    found = []
    words = set(re.findall(r"[a-z']+", lowered))
    if any((term in lowered) if " " in term else (term in words) for term in BLOCKED_TERMS):
        found.append("blocked language")
    if LINK.search(text):
        found.append("link")
    if MARKUP.search(text):
        found.append("markup")
    if CONTACT.search(text):
        found.append("contact details")
    return found
