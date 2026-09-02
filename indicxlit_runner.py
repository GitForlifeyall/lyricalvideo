"""
AI4Bharat IndicXlit Transliteration Runner
Converts Hindi (Devanagari) lyrics into Romanized Hinglish using the AI4Bharat IndicXlit transformer model.
"""

import os
import sys
import types
import json
import re
import warnings
from typing import List, Any

# Ensure utf-8 streams on Windows
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Suppress deprecation and hydra warnings
warnings.filterwarnings("ignore")
os.environ["HYDRA_FULL_ERROR"] = "0"

# Workaround: urduhack imports TensorFlow unnecessarily; stub it before ai4bharat import
urduhack_stub = types.ModuleType("urduhack")
urduhack_stub.normalize = lambda value: value
sys.modules["urduhack"] = urduhack_stub

# Global cached engine
_ENGINE = None


def get_engine() -> Any:
    global _ENGINE
    if _ENGINE is None:
        from ai4bharat.transliteration import XlitEngine
        # Initialize multilingual Indic -> English transliteration engine
        _ENGINE = XlitEngine(src_script_type="indic", beam_width=4, rescore=False)
    return _ENGINE


def clean_indic_text(text: str) -> str:
    """Normalize special Indic characters for better phonetic transliteration."""
    if not text:
        return ""
    indic_normalization = str.maketrans({
        "\u0958": "क",  # qa -> ka
        "\u095e": "फ",  # fa -> pha
        "\u0901": "ं",  # chandrabindu -> anusvara
    })
    return str(text).translate(indic_normalization)


def transliterate_lines(lines: List[str], lang_code: str = "hi") -> List[str]:
    """Transliterate a list of native Indic script lyric lines into Romanized script."""
    engine = get_engine()
    results = []
    for line in lines:
        if not line or not line.strip():
            results.append(line)
            continue
        cleaned = clean_indic_text(line)
        # Check if line contains Indic script
        if re.search(r'[\u0900-\u097F\u0A00-\u0A7F]', cleaned):
            try:
                translit = engine.translit_sentence(cleaned, lang_code=lang_code)
                # Normalize danda and Hindi punctuation
                translit = translit.replace("।", ".").replace("॥", ".").replace("\u093c", "").strip()
                results.append(translit)
            except Exception as err:
                results.append(cleaned)
        else:
            results.append(line)
    return results


def main():
    raw_input = ""
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if os.path.exists(arg):
            with open(arg, "r", encoding="utf-8") as f:
                raw_input = f.read()
        else:
            raw_input = arg
    else:
        raw_input = sys.stdin.read()

    if not raw_input.strip():
        print("__INDICXLIT_RESULT__" + json.dumps([]))
        return

    try:
        data = json.loads(raw_input)
        if isinstance(data, str):
            lines = [data]
        elif isinstance(data, list):
            lines = [str(x) for x in data]
        else:
            lines = [str(data)]
    except Exception:
        lines = [line for line in raw_input.splitlines() if line]

    results = transliterate_lines(lines, lang_code="hi")
    print("__INDICXLIT_RESULT__" + json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
