"""Everything that depends on the user's language (English, French, Arabic) in one place.

The phone sends the language code ("en", "fr", "ar"); we never guess the language ourselves.
"""

LANGUAGE_NAMES = {"en": "English", "fr": "French", "ar": "Arabic"}

# Exactly the same sentences as the phone app (mobile/lib/languages.dart).
NOT_SURE = {
    "en": "I'm not sure.",
    "fr": "Je ne suis pas sûr.",
    "ar": "لست متأكداً.",
}

# Short reason added after "I'm not sure", so the user knows what went wrong.
NOT_SURE_REASONS = {
    "no_recent": {
        "en": "I don't have a recent image.",
        "fr": "Je n'ai pas d'image récente.",
        "ar": "ليس لدي صورة حديثة.",
    },
    "no_match": {
        "en": "I didn't see anything about that.",
        "fr": "Je n'ai rien vu à ce sujet.",
        "ar": "لم أرَ شيئاً عن ذلك.",
    },
    "no_text": {
        "en": "I didn't see any text recently.",
        "fr": "Je n'ai pas vu de texte récemment.",
        "ar": "لم أرَ أي نص مؤخراً.",
    },
    "no_model": {
        "en": "I can't analyse the image right now.",
        "fr": "Je ne peux pas analyser l'image pour le moment.",
        "ar": "لا أستطيع تحليل الصورة الآن.",
    },
}

# Unprompted warnings (alerts.py). They only say what was seen: never "safe".
ALERT_TEXTS = {
    "stairs": {
        "en": "Stairs ahead.",
        "fr": "Escalier devant vous.",
        "ar": "درج أمامك.",
    },
    "door": {
        "en": "Door ahead.",
        "fr": "Porte devant vous.",
        "ar": "باب أمامك.",
    },
}

# Words that decide the ROUTE of a question (checked in this order: text, then now; else past).
# English words are always checked too, because people often mix languages.
ROUTE_KEYWORDS = {
    "text": {
        "en": ["sign", "say", "says", "said", "written", "write", "text", "read", "label", "plate"],
        "fr": ["panneau", "écrit", "écrite", "dit", "texte", "lire", "affiche", "plaque", "inscription"],
        "ar": ["لافتة", "اللافتة", "مكتوب", "تقول", "يقول", "نص", "اقرأ", "كتب", "لوحة", "اللوحة"],
    },
    "now": {
        "en": ["now", "in front of me", "ahead of me", "what do you see", "what can you see", "around me"],
        "fr": ["maintenant", "devant moi", "en face", "que vois-tu", "tu vois", "autour de moi", "actuellement"],
        "ar": ["الآن", "الان", "أمامي", "امامي", "قدامي", "ماذا ترى", "حولي"],
    },
}

# Common short words ignored when we pick keywords to search in the OCR text.
STOPWORDS = {
    "en": {"what", "does", "did", "the", "that", "this", "there", "was", "were", "is", "are", "say",
           "says", "said", "sign", "written", "text", "read", "door", "just", "passed", "with", "have"},
    "fr": {"quoi", "que", "qu'est-ce", "est", "était", "dit", "panneau", "écrit", "texte", "porte",
           "cette", "celle", "avec", "dans", "pour", "vient", "passé", "passée", "sur", "les", "des"},
    "ar": {"ماذا", "ما", "هل", "هذه", "هذا", "التي", "الذي", "على", "في", "من", "تقول", "اللافتة",
           "لافتة", "مكتوب", "الباب"},
}

# The assistant must NEVER say something is safe. Any sentence matching one of these
# (in any of the three languages, since models sometimes switch language) is removed.
# Note: "pas sûr" (= not sure) is allowed, so "Je ne suis pas sûr" is kept.
SAFE_PATTERNS = [
    r"\bsafe(ly|ty)?\b", r"\bno danger\b", r"\bdanger[- ]free\b", r"\bhazard[- ]free\b",
    r"\bsans danger\b", r"\bsans risque\b", r"\ben sécurité\b", r"\bsécuritaire\b", r"\bsécurisée?s?\b",
    r"(?<!pas )\bsûre?s?\b",
    r"آمن", r"أمان", r"مأمون", r"لا خطر", r"بدون خطر",
]


def normalize_language(code):
    """Return "en", "fr" or "ar". Unknown codes fall back to English (like the phone app)."""
    code = (code or "").lower()[:2]
    return code if code in LANGUAGE_NAMES else "en"


def not_sure(language, reason=None):
    """'I'm not sure.' in the user's language, plus a short reason if given."""
    text = NOT_SURE[language]
    if reason:
        text += " " + NOT_SURE_REASONS[reason][language]
    return text
