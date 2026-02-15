"""
Text utilities for cleaning OpenClaw response text.
Strips markdown syntax and removes emoji characters that render as boxes
on systems without emoji fonts. Zero external dependencies (stdlib re only).
"""

import re


def strip_markdown(text: str) -> str:
    """Strip markdown syntax, keeping the readable content."""
    if not text:
        return text

    # Fenced code blocks → [code]
    text = re.sub(r'```[\s\S]*?```', '[code]', text)

    # Inline code → just the text
    text = re.sub(r'`([^`]+)`', r'\1', text)

    # Images ![alt](url) → alt
    text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', text)

    # Links [text](url) → text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

    # Headings: strip leading #s
    text = re.sub(r'(?m)^#{1,6}\s+', '', text)

    # Bold/italic combos: ***text*** or ___text___
    text = re.sub(r'\*{3}(.+?)\*{3}', r'\1', text)
    text = re.sub(r'_{3}(.+?)_{3}', r'\1', text)

    # Bold: **text** or __text__
    text = re.sub(r'\*{2}(.+?)\*{2}', r'\1', text)
    text = re.sub(r'_{2}(.+?)_{2}', r'\1', text)

    # Italic: *text* or _text_ (word-boundary aware to avoid false positives)
    text = re.sub(r'(?<!\w)\*([^*]+)\*(?!\w)', r'\1', text)
    text = re.sub(r'(?<!\w)_([^_]+)_(?!\w)', r'\1', text)

    # Strikethrough: ~~text~~
    text = re.sub(r'~~(.+?)~~', r'\1', text)

    # Blockquotes: strip leading >
    text = re.sub(r'(?m)^>\s?', '', text)

    # Unordered list markers: - or * at line start → bullet
    text = re.sub(r'(?m)^[\s]*[-*+]\s+', '\u2022 ', text)

    # Ordered list markers: 1. 2. etc → keep number with bullet style
    text = re.sub(r'(?m)^[\s]*\d+\.\s+', '\u2022 ', text)

    # Horizontal rules
    text = re.sub(r'(?m)^[-*_]{3,}\s*$', '', text)

    return text


def clean_emoji(text: str) -> str:
    """Remove emoji codepoints that would render as tofu boxes."""
    if not text:
        return text

    # Comprehensive emoji Unicode ranges
    emoji_pattern = re.compile(
        '['
        '\U0001F600-\U0001F64F'  # Emoticons
        '\U0001F300-\U0001F5FF'  # Misc symbols & pictographs
        '\U0001F680-\U0001F6FF'  # Transport & map symbols
        '\U0001F1E0-\U0001F1FF'  # Flags
        '\U0001F900-\U0001F9FF'  # Supplemental symbols
        '\U0001FA00-\U0001FA6F'  # Chess symbols
        '\U0001FA70-\U0001FAFF'  # Symbols extended-A
        '\U00002702-\U000027B0'  # Dingbats
        '\U0000FE00-\U0000FE0F'  # Variation selectors
        '\U0000200D'             # Zero-width joiner
        '\U000020E3'             # Combining enclosing keycap
        '\U00002600-\U000026FF'  # Misc symbols
        '\U00002300-\U000023FF'  # Misc technical
        '\U0000203C-\U00003299'  # CJK symbols + enclosed
        ']+',
        flags=re.UNICODE
    )
    return emoji_pattern.sub('', text)


def truncate_at_sentence(text: str, max_chars: int = 500) -> str:
    """Truncate text at the nearest sentence boundary within max_chars.

    Searches backwards from max_chars for sentence-ending punctuation (.!?)
    followed by whitespace or end of string. Falls back to word boundary,
    then hard cut if needed.
    """
    if not text or len(text) <= max_chars:
        return text

    # Search backwards for sentence boundary
    search_region = text[:max_chars]
    min_pos = max_chars // 3  # Only use sentence boundary if >1/3 preserved

    best = -1
    for i in range(len(search_region) - 1, min_pos - 1, -1):
        if search_region[i] in '.!?' and (i + 1 >= len(search_region) or search_region[i + 1] in ' \n\t\r'):
            best = i + 1
            break

    if best > 0:
        return text[:best].rstrip()

    # Fall back to word boundary
    space_pos = search_region.rfind(' ', min_pos)
    if space_pos > 0:
        return text[:space_pos].rstrip() + "..."

    # Hard cut
    return text[:max_chars].rstrip() + "..."


def clean_response_text(text: str) -> str:
    """Clean OpenClaw response text: strip markdown then remove emoji."""
    if not text:
        return text
    text = strip_markdown(text)
    text = clean_emoji(text)
    # Collapse multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
