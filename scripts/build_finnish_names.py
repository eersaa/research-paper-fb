"""Build data/finnish_names.json — a static list of traditional Finnish given names.

No network calls. Idempotent. Running twice produces byte-identical output.
"""

import json
from pathlib import Path

MALE_NAMES: list[str] = [
    "Antti",
    "Arto",
    "Eero",
    "Hannu",
    "Harri",
    "Heikki",
    "Ilkka",
    "Jari",
    "Jouni",
    "Juha",
    "Juhani",
    "Kari",
    "Kimmo",
    "Lauri",
    "Markku",
    "Matti",
    "Mikko",
    "Olli",
    "Paavo",
    "Pekka",
    "Pentti",
    "Petri",
    "Rauno",
    "Risto",
    "Sami",
    "Seppo",
    "Tapio",
    "Timo",
    "Vesa",
    "Ville",
]

FEMALE_NAMES: list[str] = [
    "Aila",
    "Aino",
    "Anna",
    "Elina",
    "Eeva",
    "Hanna",
    "Jaana",
    "Kaarina",
    "Kaisa",
    "Kirsi",
    "Laura",
    "Leena",
    "Liisa",
    "Maija",
    "Maria",
    "Mervi",
    "Minna",
    "Niina",
    "Päivi",
    "Pirjo",
    "Raija",
    "Riikka",
    "Riitta",
    "Sari",
    "Satu",
    "Siiri",
    "Tarja",
    "Tiina",
    "Tuija",
    "Tuulikki",
]

OUTPUT_FILE = Path(__file__).parent.parent / "data" / "finnish_names.json"


def build() -> None:
    combined = sorted(set(MALE_NAMES) | set(FEMALE_NAMES))
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(combined, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(combined)} names to {OUTPUT_FILE}")


if __name__ == "__main__":
    build()
