#!/usr/bin/env python3
"""Catalog of our games: validate apps.json and (re)build apps.html from it.

  python3 tools/apps_catalog.py check   # validate apps.json + icons, and that apps.html is up to date (exit 1 on error)
  python3 tools/apps_catalog.py build   # validate, then rewrite apps.html

Stdlib only. The games read apps.json with their own strict parser; this script enforces the same rules here so a
bad push is caught before the games ever see it.
"""
import html
import json
import os
import re
import struct
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ["en", "uk", "fr", "de", "es", "pt"]
LANG_NAMES = {"en": "English", "uk": "Українська", "fr": "Français", "de": "Deutsch", "es": "Español", "pt": "Português"}
PAGE_BASE = "https://foxgames-app.github.io/lysko/"
# same limits as the game's reader (Lysko Wash KidsCatalog.cs): fullmatch, 64 KB, 30 apps, name 40 / text 90 chars
ICON_RE = re.compile(r"https://foxgames-app\.github\.io/lysko/apps/[a-z0-9_]{1,60}\.png")
ID_RE = re.compile(r"[a-z0-9_]{1,40}")
PKG_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+")
MAX_BYTES, MAX_APPS = 64 * 1024, 30
SOON = {"en": "Coming soon", "uk": "Незабаром", "fr": "Bientôt", "de": "Demnächst", "es": "Próximamente", "pt": "Em breve"}
TITLE = {"en": "Our games", "uk": "Наші ігри", "fr": "Nos jeux", "de": "Unsere Spiele", "es": "Nuestros juegos", "pt": "Nossos jogos"}
LINKS = {"en": ("Google Play", "App Store"), "uk": ("Google Play", "App Store"), "fr": ("Google Play", "App Store"),
         "de": ("Google Play", "App Store"), "es": ("Google Play", "App Store"), "pt": ("Google Play", "App Store")}


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise ValueError("not a PNG")
    return struct.unpack(">II", head[16:24])


def _no_dup_keys(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError(f"duplicate key {k!r}")
        d[k] = v
    return d


def load(path):
    """strict load: size cap, UTF-8, no duplicate keys (the game rejects such files)"""
    raw = open(path, "rb").read()
    if len(raw) > MAX_BYTES:
        raise ValueError(f"apps.json over {MAX_BYTES} bytes")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_no_dup_keys)


def validate(doc):
    errs = []
    sch = doc.get("schema") if isinstance(doc, dict) else None
    if type(sch) is not int or sch != 1:
        return ["top level: object with \"schema\": 1 required"]
    apps = doc.get("apps")
    if not isinstance(apps, list) or not apps:
        return ["\"apps\" must be a non-empty list"]
    if len(apps) > MAX_APPS:
        errs.append(f"more than {MAX_APPS} apps (the game reads only the first {MAX_APPS})")
    seen = set()
    for i, a in enumerate(apps):
        p = f"apps[{i}]"
        if not isinstance(a, dict):
            errs.append(f"{p}: not an object"); continue
        aid = a.get("id")
        if not isinstance(aid, str) or not ID_RE.fullmatch(aid):
            errs.append(f"{p}: bad id {aid!r}")
        elif aid in seen:
            errs.append(f"{p}: duplicate id {aid}")
        seen.add(aid)
        if not isinstance(a.get("coming_soon"), bool):
            errs.append(f"{p}: coming_soon must be true/false")
        icon = a.get("icon")
        if not isinstance(icon, str) or not ICON_RE.fullmatch(icon):
            errs.append(f"{p}: icon must be {PAGE_BASE}apps/<name>.png")
        else:
            local = os.path.join(ROOT, icon[len(PAGE_BASE):])
            if not os.path.isfile(local):
                errs.append(f"{p}: icon file missing in repo: {local}")
            else:
                try:
                    w, h = png_size(local)
                    if w != h or not 256 <= w <= 512:
                        errs.append(f"{p}: icon must be square 256-512 px, is {w}x{h}")
                    if os.path.getsize(local) > 300_000:
                        errs.append(f"{p}: icon over 300 KB")
                except ValueError as e:
                    errs.append(f"{p}: icon {e}")
        an = a.get("android")
        if an is not None:
            pkg = an.get("package") if isinstance(an, dict) else None
            if not isinstance(pkg, str) or not PKG_RE.fullmatch(pkg):
                errs.append(f"{p}: android.package invalid")
            elif an.get("url") != f"https://play.google.com/store/apps/details?id={pkg}":
                errs.append(f"{p}: android.url must be https://play.google.com/store/apps/details?id={pkg}")
        io = a.get("ios")
        if io is not None:
            iid = io.get("id") if isinstance(io, dict) else None
            if not isinstance(iid, str) or not re.fullmatch(r"[0-9]{6,12}", iid):
                errs.append(f"{p}: ios.id must be the numeric App Store id")
            elif io.get("url") != f"https://apps.apple.com/app/id{iid}":
                errs.append(f"{p}: ios.url must be https://apps.apple.com/app/id{iid}")
        if a.get("coming_soon") is False and an is None and io is None:
            errs.append(f"{p}: a published app needs at least one store link")
        for key, maxlen in (("name", 40), ("text", 90)):
            d = a.get(key)
            if not isinstance(d, dict):
                errs.append(f"{p}: {key} must be an object of languages"); continue
            for lang in LANGS:
                v = d.get(lang)
                if (not isinstance(v, str) or not v.strip() or len(v) > maxlen or "<" in v or ">" in v
                        or any(unicodedata.category(c) == "Cc" for c in v)):
                    errs.append(f"{p}: {key}.{lang} missing, too long (>{maxlen}), control chars or < >")
            extra = set(d) - set(LANGS)
            if extra:
                errs.append(f"{p}: {key} has unknown languages {sorted(extra)}")
        extra = set(a) - {"id", "coming_soon", "icon", "android", "ios", "name", "text"}
        if extra:
            errs.append(f"{p}: unknown keys {sorted(extra)}")
    return errs


def render(doc):
    e = html.escape
    out = ["<!DOCTYPE html>", '<html lang="en">', "<head>", '<meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1">',
           "<title>Fox Games — our games</title>",
           "<style>body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:760px;margin:0 auto;padding:24px 18px;"
           "line-height:1.5;color:#2b2b2b}h1{font-size:1.5em;color:#c76a14}h2{font-size:1.2em;margin-top:2em;border-top:1px solid #eee;"
           "padding-top:1em}nav a{margin-right:12px}.app{display:flex;gap:16px;align-items:center;margin:14px 0}"
           ".app img{width:96px;height:96px;border-radius:22px;flex:none}.app p{margin:2px 0}.soon{color:#888}"
           ".soon img{opacity:.55}</style>",
           "</head>", "<body>",
           "<!-- generated from apps.json by tools/apps_catalog.py build; do not edit by hand -->",
           "<nav>" + "".join(f'<a href="#{l}">{LANG_NAMES[l]}</a>' for l in LANGS) + "</nav>"]
    for k, lang in enumerate(LANGS):
        tag = "h1" if k == 0 else "h2"
        out.append(f'<section id="{lang}" lang="{lang}">')
        out.append(f"<{tag}>Fox Games — {e(TITLE[lang])}</{tag}>")
        for a in doc["apps"]:
            soon = a["coming_soon"]
            links = []
            if a.get("android"):
                links.append(f'<a href="{e(a["android"]["url"])}">{LINKS[lang][0]}</a>')
            if a.get("ios"):
                links.append(f'<a href="{e(a["ios"]["url"])}">{LINKS[lang][1]}</a>')
            if soon:
                links = [e(SOON[lang])]
            out.append(f'<div class="app{" soon" if soon else ""}"><img src="apps/{e(os.path.basename(a["icon"]))}" alt="">'
                       f'<div><p><b>{e(a["name"][lang])}</b></p><p>{e(a["text"][lang])}</p><p>{" · ".join(links)}</p></div></div>')
        out.append("</section>")
    out += ['<p><small><a href="privacy.html">Privacy Policy</a> · <a href="apps.json">apps.json</a></small></p>', "</body>", "</html>", ""]
    return "\n".join(out)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    try:
        doc = load(os.path.join(ROOT, "apps.json"))
    except ValueError as e:
        print(f"apps.json INVALID: {e}"); return 1
    errs = validate(doc)
    if errs:
        print("apps.json INVALID:\n  " + "\n  ".join(errs)); return 1
    page = render(doc)
    path = os.path.join(ROOT, "apps.html")
    if cmd == "build":
        with open(path, "w", encoding="utf-8") as f:
            f.write(page)
        print(f"apps.html written ({len(doc['apps'])} apps)"); return 0
    cur = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    if cur != page:
        print("apps.html is out of date: run python3 tools/apps_catalog.py build"); return 1
    print(f"apps.json OK ({len(doc['apps'])} apps), apps.html up to date"); return 0


if __name__ == "__main__":
    sys.exit(main())
