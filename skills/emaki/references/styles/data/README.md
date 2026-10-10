Data (dark): a calm dashboard that tells one number at a time; counters, growing bars, drawn lines, one hero metric per scene.

Use when: metrics, reports, investor/client updates, "year in numbers", product analytics stories.
Signature moves: `load_csv("data/x.csv")`; `Counter(0, value, t, sound="tick")` as the hero; `BarChart(..., highlight=[i])`; `LineChart(..., area=True, tip=True)`; `Donut`; chart inside a `Card`; caption with the data source; one idea per scene.
Avoid: 3D charts, rainbow palettes, more than 2 series at once, effects on numbers.
Fonts: Lato and Noto Sans Mono (free, often preinstalled on Linux). Better: Inter or IBM Plex Sans (tabular figures), JetBrains Mono for raw values.
