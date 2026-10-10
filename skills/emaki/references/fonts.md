# Fonts

The on-screen language comes from brief.yaml `language` (default `en`). A font qualifies when it
has every glyph the copy uses: QA `glyphs` fails any missing character. Ukrainian copy (`uk`) is
strict before rendering too: the engine skips fonts without the full Ukrainian alphabet
(including Ґ Є І Ї) and the typographic apostrophe ’ (U+2019, write «пам’ять», not «пам'ять»).

Lookup order: `<project>/fonts/` -> `motion-lib/fonts/` (if you keep a library) -> system fonts
(`setup_env.sh` prints the ones with Ukrainian coverage) -> DejaVu fallback (QA warns). External
fonts come only from the user: when the style needs a font that is not available, name ONE
specific free font and where to get it (fonts.google.com), keep working on the closest available
font, and swap it in when the user drops the file into fonts/.

## Free fonts by role (Google Fonts, OFL; all of these also cover Ukrainian)

| feel | display | text | mono |
|---|---|---|---|
| neutral product / tech | Inter, Manrope, Onest, Golos Text | Inter, Golos Text | JetBrains Mono, IBM Plex Mono |
| editorial / premium | Playfair Display, Cormorant Garamond, Lora, Literata | Source Serif 4, PT Serif, Inter | IBM Plex Mono |
| italic serif accent inside a sans line (r03) | Instrument Serif*, Playfair Display Italic, Lora Italic | | |
| bold social / playful | Unbounded, Nunito, Comfortaa, Montserrat Alternates | Nunito, Manrope | Fira Code |
| corporate / data | IBM Plex Sans, Montserrat, Raleway | IBM Plex Sans, Roboto | Roboto Mono |
| condensed / poster | Oswald, Roboto Condensed | Roboto Condensed | |
| thin elegant (r04) | Manrope ExtraLight, Inter Light, Raleway Light | | |

*check Cyrillic in the current release before recommending it for Ukrainian copy; otherwise
Playfair Display Italic.

After the user adds a font, re-run `setup_env.sh` (font index refresh) and check the QA
`glyphs` and `fonts` lines. For Ukrainian, Ґ, Є, І, Ї and ’ are the usual gaps.

## Currency and numbers

The currency sign is part of the copy (`Counter(..., prefix="$")`, `suffix=" ₴"`, `suffix=" €"`);
check it in the `glyphs` line, since ₴ (U+20B4) is missing from many fonts (Lato, Lora, Carlito,
Liberation, DejaVu and Noto Sans Mono have it; otherwise write «грн»). Numbers: English copy
uses a comma for thousands and a decimal point (`sep=",", dec="."`); Ukrainian copy a thin space
for thousands and a decimal comma (the default; Counter falls back from U+202F to U+00A0 when
the font lacks it).

## Fonts often preinstalled on Linux with Ukrainian coverage

Lato (thin..black), Lora (variable 400-700, roman and italic), Carlito, Liberation Sans/Serif/Mono,
Nimbus Sans / Roman / Mono PS (Helvetica/Times/Courier clones), URW Gothic (Avant Garde clone),
C059, P052 (roman and italic), URW Bookman, Noto Sans Mono, Noto Mono, DejaVu Sans/Serif/Mono.
On macOS, add the fonts you need to the project's fonts/ folder.

## After Effects

AE needs the same fonts installed on the user's machine. The exporter writes PostScript names;
the script checks them on AE 24+ and lists them in out/ae/README.md.
