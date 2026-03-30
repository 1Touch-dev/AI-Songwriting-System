"""
LLM Generator
=============
Sends the assembled prompt to OpenAI and returns generated lyrics.

Usage:
    from rag.generator import generate_lyrics
    lyrics = generate_lyrics(system_prompt, user_prompt)
"""

import os
import time

from dotenv import load_dotenv

load_dotenv()

import openai

from utils.config import GENERATION_MODEL

_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generate_lyrics(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.85,
    max_tokens: int = 1200,
) -> str:
    """
    Generate song lyrics using OpenAI.

    Parameters
    ----------
    system_prompt : str
    user_prompt   : str
    temperature   : float  (0.7–0.9 per spec)
    max_tokens    : int

    Returns
    -------
    str  Generated lyrics text
    """
    for attempt in range(3):
        try:
            response = _client.chat.completions.create(
                model=GENERATION_MODEL,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return response.choices[0].message.content.strip()
        except openai.RateLimitError:
            wait = 2 ** (attempt + 2)
            print(f"[RateLimit] waiting {wait}s …")
            time.sleep(wait)
        except openai.APIError as exc:
            raise RuntimeError(f"OpenAI API error: {exc}") from exc

    raise RuntimeError("Generation failed after retries")
