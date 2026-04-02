"""
Strict output validator and corrector for the AI Songwriting System.
Enforces ZERO-TOLERANCE rules for choruses (3 lines exactly, 4-5 words max, exact repetition).
"""

import os
import re
import difflib
from typing import Optional
from openai import OpenAI

from utils.config import VALIDATOR_MODEL, LABELING_MODEL

_VALIDATOR_SYSTEM_PROMPT = """\
You are a STRICT output validator and corrector for a songwriting system.
You MUST enforce rules with ZERO tolerance.

----------------------------------------
TASK
----------------------------------------

1. Extract ALL [Chorus] sections from the provided song.
2. Validate each chorus against STRICT rules.
3. If ANY rule fails -> REWRITE the chorus.
4. Return FULL song with corrected choruses.

----------------------------------------
STRICT RULES (NO EXCEPTIONS)
----------------------------------------

- Be EXACTLY 3 lines (ABSOLUTE REQUIREMENT)
- Do NOT include more than 3 lines for the chorus
- Each line MUST be 4-5 words ONLY
- Use ONE central hook phrase
- Hook MUST appear EXACTLY in line 1 and line 2
- Line 3 MUST still reference the same hook (no drift)
- All lines MUST have similar rhythm
- No long phrases or explanations

----------------------------------------
FAIL CONDITIONS (MANDATORY FIX)
----------------------------------------

If ANY of the following:
- word count > 5 or < 4
- hook not repeated exactly
- rhythm mismatch
- vague or generic line

-> YOU MUST REWRITE THE CHORUS COMPLETELY

----------------------------------------
REWRITE STRATEGY
----------------------------------------

- Keep same theme and emotion
- Extract or infer a strong hook
- Simplify aggressively
- Prefer repetition over creativity
- Make it sound like a real chorus

----------------------------------------
CRITICAL BEHAVIOR
----------------------------------------

Do NOT try to preserve flawed lines.
If chorus is weak -> rewrite from scratch.

----------------------------------------
OUTPUT
----------------------------------------

Return FULL song.
Replace ONLY the chorus sections.

NO explanations. NO comments.
If chorus is already perfect -> return unchanged.
"""

# --- ANCHOR KEYWORDS ---
CONCRETE_ANCHOR_KEYWORDS = {
    "location": [
        "street", "avenue", "block", "city", "coast", "vegas", "la", "atlanta", "toronto", "hills",
        "beach", "hotel", "balcony", "room", "apartment", "club", "highway", "interstate", "valley"
    ],
    "object": [
        "car", "porsche", "benz", "rolex", "chain", "ring", "phone", "bottle", "cup", "hennessy",
        "jacket", "purse", "keys", "shoes", "heels", "watch", "camera", "mirror", "seat", "dashboard"
    ],
    "time": [
        "midnight", "morning", "evening", "friday", "saturday", "weekend", "june", "july", "winter",
        "summer", "night", "tonight", "today", "yesterday", "tomorrow", "clock", "seconds", "hours"
    ]
}

def extract_lines(text: str) -> list[str]:
    # Extract chorus lines, ignoring the [Chorus] tag
    lines = [l.strip() for l in text.split("\n") if l.strip() and not l.startswith("[")]
    return lines

def line_similarity(l1: str, l2: str) -> float:
    """Return similarity ratio between two lines."""
    return difflib.SequenceMatcher(None, l1.lower(), l2.lower()).ratio()

def extract_hook_phrase(line: str) -> str:
    """Extract a catchy phrase from a line for sync check."""
    words = line.lower().split()
    if len(words) < 3: return line.lower().strip(",.?")
    return " ".join(words[:3]).strip(",.?")

def simplicity_score(lines: list[str]) -> float:
    # Reward medium word count (4-6 words) per line
    if not lines: return 0.0
    scores = []
    for l in lines:
        wc = len(l.split())
        if 4 <= wc <= 5: scores.append(1.0) # HARDENED: 4-5 is perfect
        elif wc == 3 or wc == 6: scores.append(0.5)
        else: scores.append(0.2)
    return sum(scores) / len(scores)

def repetition_score(lines: list[str]) -> float:
    # 0.0 to 1.0. Ideal = some repetition, not 100%.
    if len(lines) < 2: return 0.0
    
    # HARD BAN: Identical triplets (A / A / A)
    if all(l.lower() == lines[0].lower() for l in lines) and len(lines) >= 3:
        return 0.1 # Very low score for pure repetition
    
    # Target Pattern: Line 1 == Line 2 (Hook Sync)
    if line_similarity(lines[0], lines[1]) > 0.9:
        return 0.9
        
    return 0.5 # Moderate repetition

def keyword_strength_score(lines: list[str]) -> float:
    text = " ".join(lines).lower()
    score = 0.0
    for cat, keywords in CONCRETE_ANCHOR_KEYWORDS.items():
        if any(k in text for k in keywords):
            score += 0.33
    return min(1.0, score)

def unique_word_ratio(lines: list[str]) -> float:
    words = " ".join(lines).lower().split()
    if not words: return 0.0
    return len(set(words)) / len(words)

def score_hook(lines: list[str]) -> float:
    if not lines: return 0.0
    
    score = 0.0
    # 1. Simplicity (good)
    score += simplicity_score(lines) * 0.3
    # 2. Repetition (required but limited)
    score += repetition_score(lines) * 0.3
    # 3. Memorability (Keywords)
    score += keyword_strength_score(lines) * 0.4
    
    # 4. FINAL HARDENING: Hard penalties
    # Line 1 and 2 mismatch
    if len(lines) >= 2 and line_similarity(lines[0], lines[1]) < 0.8:
        score -= 0.3
        
    # Line 3 too similar to Line 1 (Low variation)
    if len(lines) >= 3 and line_similarity(lines[0], lines[3] if len(lines)>3 else lines[-1]) > 0.85:
        score -= 0.3
        
    # Excessive repetition pattern
    if all(l.lower() == lines[0].lower() for l in lines):
        score = 0.1 # TOTAL FAILURE
        
    return max(0.0, min(1.0, score))

def has_concrete_anchor(lines: list[str]) -> bool:
    return keyword_strength_score(lines) > 0.3


class ChorusValidator:
    def __init__(self):
        self._client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
    def enforce_chorus_structure(self, chorus: str, lines: list[str]) -> str:
        """
        Garantuar exactly 3 lines, 4-5 words.
        """
        # HARD CUT to 3 lines
        if len(lines) > 3:
            print(f"[VALIDATOR] Hard-cutting {len(lines)} lines to 3.")
            lines = lines[:3]
            
        # HARD FIX for too few lines (Regenerate)
        if len(lines) < 3:
            print(f"[VALIDATOR] Too few lines ({len(lines)}), regenerating...")
            return self.rewrite_chorus(chorus, "too few lines (need exactly 3)")
            
        # Check word counts per line
        for i, line in enumerate(lines):
            wc = len(line.split())
            if not (4 <= wc <= 5):
                print(f"[VALIDATOR] Line {i+1} has {wc} words. Rewriting...")
                return self.rewrite_chorus(chorus, f"line {i+1} has {wc} words (need 4-5)")
        
        return "\n".join(lines)

    def quick_verify(self, lyrics: str) -> bool:
        """
        Regex-based check for the 3-line, 4-5 word chorus rule.
        Returns True if the chorus is already perfect.
        """
        chorus_match = re.search(r"\[[Cc]horus.*?\]\n(.*?)\n\n", lyrics + "\n\n", re.S)
        if not chorus_match:
            return False
            
        lines = [l.strip() for l in chorus_match.group(1).split("\n") if l.strip()]
        if len(lines) != 3:
            return False
            
        for line in lines:
            words = line.split()
            if not (4 <= len(words) <= 5):
                return False
                
        l1, l2 = lines[0].lower(), lines[1].lower()
        if line_similarity(l1, l2) < 0.9:
            return False
                
        return True

    def validate_hook(self, chorus: str) -> str:
        """
        Final Hardened Validator: Line Sync, Variation, and Structural Integrity.
        """
        lines = extract_lines(chorus)
        if not lines:
            return chorus
            
        # 1. Structural Enforcement
        chorus_text = self.enforce_chorus_structure(chorus, lines)
        if "[Chorus]" not in chorus_text: # Refetched lines after fix
            lines = extract_lines(chorus_text)
        else:
            return chorus_text

        # 2. Hook Quality Floor & Creative Enforcement
        reason = None
        
        # RULE: Line 1 & 2 MUST share same hook phrase
        if len(lines) >= 2:
            h1 = extract_hook_phrase(lines[0])
            if h1 not in lines[1].lower():
                reason = "line 1 and 2 hook mismatch"
        
        # RULE: STRONG VARIATION (Line 1 vs Line 3)
        if not reason and len(lines) >= 3:
            if line_similarity(lines[0], lines[2]) > 0.85:
                reason = "line 3 too similar to line 1 (need variation)"
                
        # RULE: Hard Ban identical triplets
        if not reason and all(l.lower() == lines[0].lower() for l in lines):
            reason = "identical triplets detected (ban)"
            
        # RULE: Concrete Anchor
        if not reason and not has_concrete_anchor(lines):
            reason = "no grounding (no location/object/time)"

        if reason:
            print(f"[VALIDATOR] Reinforcing hook Quality: {reason}")
            return self.rewrite_chorus(chorus_text, reason)
            
        return f"[Chorus]\n{chorus_text}"

    def rewrite_chorus(self, chorus: str, reason: str) -> str:
        prompt = f"""
Rewrite this [Chorus] to be more effective.
Problem: {reason}

STRICT RULES (MANDATORY):
1. MUST include a concrete anchor (Location, Object, or Time).
2. MUST have rhythmic repetition (Line 1 and Line 2 MUST be nearly identical).
3. MUST have strong variation (Line 3 MUST be different from Line 1).
4. EXACTLY 3 lines.
5. EXACTLY 4-5 words per line.

Current Chorus:
{chorus}

Respond ONLY with the corrected [Chorus].
"""
        try:
            res = self._client.chat.completions.create(
                model=LABELING_MODEL,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}]
            )
            corrected = res.choices[0].message.content.strip()
            # Safety: Ensure the [Chorus] tag is present if desired by pipeline
            if not corrected.startswith("[Chorus]"):
                corrected = f"[Chorus]\n{corrected}"
            return corrected
        except:
            return chorus

    def validate_and_fix(self, lyrics: str) -> str:
        """Full song validator pass."""
        if not lyrics or "[Chorus]" not in lyrics:
            return lyrics
            
        if self.quick_verify(lyrics):
            return lyrics
            
        try:
            response = self._client.chat.completions.create(
                model=VALIDATOR_MODEL,
                temperature=0.3,
                max_tokens=2000,
                messages=[
                    {"role": "system", "content": _VALIDATOR_SYSTEM_PROMPT},
                    {"role": "user", "content": lyrics},
                ],
            )
            corrected_lyrics = response.choices[0].message.content.strip()
            if "[Verse" in corrected_lyrics or "[Intro]" in corrected_lyrics:
                return corrected_lyrics
            return lyrics
        except Exception as e:
            print(f"Validator Error: {e}")
            return lyrics
