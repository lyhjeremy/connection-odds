"""Fill site templates from site/numbers.json and inline the SVG figures.

site/index.template.html     -> index.html
site/overview.fragment.html  -> ../../_ai-projects-tooling/overview-pages/fragments/connection-odds.html
site/README.template.md      -> README.md
{{name}} is a number from numbers.json; {{FIG:file}} inlines figures/file.svg. Only the
first inlined SVG on a page keeps its <style> block, since all share one stylesheet.
Run the overview builder and fixdims.py afterwards.
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLING = ROOT.parent.parent / "_ai-projects-tooling/overview-pages/fragments/connection-odds.html"


def fill(text: str, n: dict, where: str, inline_figs: bool = True) -> str:
    missing = sorted(set(re.findall(r"\{\{(\w+)\}\}", text)) - set(n))
    if missing:
        raise SystemExit(f"numbers missing in {where}: {missing}")
    text = re.sub(r"\{\{(\w+)\}\}", lambda m: str(n[m.group(1)]), text)
    if inline_figs:
        seen = [False]

        def fig(m):
            s = (ROOT / "figures" / m.group(1)).read_text()
            s = s.replace('xmlns="http://www.w3.org/2000/svg" ', "")
            if seen[0]:
                s = re.sub(r"<style>.*?</style>", "", s, flags=re.S)
            seen[0] = True
            return s.strip()
        text = re.sub(r"\{\{FIG:([\w.]+)\}\}", fig, text)
    if "—" in text:
        raise SystemExit(f"em dash in {where}")
    return text


def main():
    n = json.loads((ROOT / "site/numbers.json").read_text())
    (ROOT / "index.html").write_text(fill((ROOT / "site/index.template.html").read_text(), n, "index"))
    frag = fill((ROOT / "site/overview.fragment.html").read_text(), n, "overview")
    if TOOLING.parent.exists():
        TOOLING.write_text(frag)
    (ROOT / "README.md").write_text(fill((ROOT / "site/README.template.md").read_text(), n, "README", False))
    print("index.html, README.md and the overview fragment written")


if __name__ == "__main__":
    main()
