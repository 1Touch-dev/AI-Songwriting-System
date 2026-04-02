
import os
import sys
import json

# Add the project root to sys.path
sys.path.append(os.getcwd())

from rag.pipeline import SongwritingPipeline

def run_test(name, artists, theme, structure, style_strength=0.8):
    print(f"\n>>>> AUDIT TEST: {name} <<<<")
    print(f"Params: Artists={artists}, Theme={theme}, Style={style_strength}")
    pipe = SongwritingPipeline()
    try:
        result = pipe.run(
            artists=artists if isinstance(artists, list) else [artists],
            theme=theme,
            structure=structure,
            style_strength=style_strength
        )
        print(f"RESULT: {len(result['lyrics'])} chars generated.")
        print("LYRICS SNIPPET:")
        print(result['lyrics'][:400] + "...")
        return result
    except Exception as e:
        print(f"ERROR: {e}")
        return None

def main():
    # Phase 2: Reproducibility
    # QA_01: Drake - Heartbreak
    run_test("QA_01_REPRODUCTION", ["Drake"], "heartbreak", "Verse 1 → Chorus → Verse 2 → Chorus", 0.8)
    
    # QA_19: Kendrick Lamar - Social Justice
    run_test("QA_19_REPRODUCTION", ["Kendrick Lamar"], "Social Justice", "Verse 1 → Chorus → Verse 2 → Chorus → Bridge → Chorus → Outro", 1.0)
    
    # New Case: SZA - Nostalgia
    run_test("SZA_NOSTALGIA", ["SZA"], "Nostalgia", "Verse 1 → Chorus → Verse 2 → Chorus", 0.8)

    # Phase 4: Adversarial
    # Non-existent artist
    run_test("NON_EXISTENT_ARTIST", ["The Screaming Void"], "Lament", "Verse 1 → Chorus", 0.8)
    
    # Extreme Style Conflict
    run_test("STYLE_CONFLICT", ["Enya"], "Aggressive Industrial Techno, heavy bass, chaos", 0.9)

if __name__ == "__main__":
    main()
