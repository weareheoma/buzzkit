#!/usr/bin/env python3
"""Buzzkit builder.

Reads news feeds (English and Swahili), your own stories (posts.txt) and the
hide list (hide.txt), then writes index.html. GitHub runs this on a schedule.
Needs only Python 3.8+. Run locally with:  python3 build.py
"""
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

# (source name, language, url, category). Add or remove lines to change your sources.
# Categories shown in the menu: World, Africa, Local (your own posts). You can invent more.
CHANNEL_URL = ""   # paste your WhatsApp Channel link here to show the "Join" block
CONTACT_EMAIL = "" # shown in the footer as a pitch address (optional)
FEEDS = [
    ("BBC News", "en", "https://feeds.bbci.co.uk/news/world/rss.xml", "World"),
    ("BBC Africa", "en", "https://feeds.bbci.co.uk/news/world/africa/rss.xml", "Africa"),
    ("Al Jazeera", "en", "https://www.aljazeera.com/xml/rss/all.xml", "World"),
    # Reuters stopped its public RSS in 2020. This Google News query lists Reuters headlines.
    ("Reuters", "en", "https://news.google.com/rss/search?q=when:1d+source:reuters&hl=en-US&gl=US&ceid=US:en", "World"),
    ("BBC Swahili", "sw", "https://feeds.bbci.co.uk/swahili/rss.xml", "World"),
    ("DW Kiswahili", "sw", "https://rss.dw.com/rdf/rss-sw-all", "World"),
]
PER_FEED = 15       # newest stories kept from each feed
KEEP_DAYS = 7       # feed stories older than this are dropped
SNIPPET = 240       # characters of summary shown
EAT = timezone(timedelta(hours=3))  # Dar es Salaam time


def local(tag):
    return tag.rsplit("}", 1)[-1]


def clean(text, limit=None):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    if limit and len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0] + "…"
    return text


def parse_date(value):
    value = (value or "").strip()
    if not value:
        return datetime.now(timezone.utc)
    try:
        d = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(timezone.utc)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def parse_feed(xml_bytes, source, lang):
    """Handles RSS 2.0 and RSS 1.0 (RDF). Returns story dicts."""
    root = ET.fromstring(xml_bytes)
    out = []
    for item in root.iter():
        if local(item.tag) != "item":
            continue
        f = {local(c.tag): (c.text or "") for c in item}
        title = clean(f.get("title"))
        link = (f.get("link") or "").strip()
        if source == "Reuters":
            title = re.sub(r"\s+-\s+Reuters$", "", title)
        if not title or not link.startswith(("http://", "https://")):
            continue
        summary = clean(f.get("description"), SNIPPET)
        if source == "Reuters" or summary == title:
            summary = ""
        out.append({
            "title": title[:200], "summary": summary, "url": link,
            "source": source, "lang": lang, "own": False, "cat": "World", "image": "", "pinned": False,
            "when": parse_date(f.get("pubDate") or f.get("date")),
        })
    out.sort(key=lambda s: s["when"], reverse=True)
    return out[:PER_FEED]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "HabariDesk/1.0 (+rss reader)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def read_posts(path="posts.txt"):
    """Your own stories. Blocks split by a line of ---; header lines, blank line, text."""
    try:
        raw = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        return []
    posts = []
    for block in re.split(r"^---\s*$", raw, flags=re.M):
        head, body, in_body = {}, [], False
        for line in block.splitlines():
            if in_body:
                body.append(line)
            elif line.strip().startswith("#"):
                continue
            elif not line.strip():
                if head:
                    in_body = True
            elif ":" in line:
                k, v = line.split(":", 1)
                head[k.strip().lower()] = v.strip()
        title = head.get("title", "").strip()
        if not title:
            continue
        try:
            when = datetime.strptime(head["date"], "%Y-%m-%d %H:%M").replace(tzinfo=EAT)
        except (KeyError, ValueError):
            when = datetime.now(timezone.utc)
        link = head.get("link", "")
        posts.append({
            "title": title[:200], "summary": "\n".join(body).strip()[:2000],
            "url": link if link.startswith(("http://", "https://")) else "",
            "source": head.get("source") or "Buzzkit",
            "lang": "sw" if head.get("lang", "en").lower().startswith("s") else "en",
            "own": True, "when": when.astimezone(timezone.utc),
            "cat": head.get("category") or "Local",
            "image": head.get("image", "") if head.get("image", "").startswith("https://") else "",
            "pinned": head.get("pinned", "").lower() in ("yes", "true", "1"),
        })
    return posts


def read_hide(path="hide.txt"):
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except FileNotFoundError:
        return []
    return [l.strip().lower() for l in lines if l.strip() and not l.strip().startswith("#")]


def is_hidden(story, hide):
    return any(h in story["url"].lower() or h in story["title"].lower() for h in hide)



SW_DAYS = ["Jumatatu", "Jumanne", "Jumatano", "Alhamisi", "Ijumaa", "Jumamosi", "Jumapili"]
SW_MONTHS = ["Januari", "Februari", "Machi", "Aprili", "Mei", "Juni", "Julai", "Agosti",
             "Septemba", "Oktoba", "Novemba", "Desemba"]
SW_MONTHS_SHORT = ["Jan", "Feb", "Mac", "Apr", "Mei", "Jun", "Jul", "Ago", "Sep", "Okt", "Nov", "Des"]
EN_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December"]
EN_MONTHS_SHORT = [m[:3] for m in EN_MONTHS]
CAT_SW = {"World": "Dunia", "Africa": "Afrika", "Local": "Hapa Kwetu"}
CAT_ORDER = ["World", "Africa", "Local"]
e = html.escape

# Everything a reader sees, once per language. Edit the wording here.
TXT = {
    "en": {
        "other": "sw", "other_name": "Kiswahili", "all": "All", "search": "Search",
        "cats": "Categories", "hero": "Morning read", "recent": "Recent stories",
        "desk": "From the desk", "more": "More headlines", "none": "No stories match.",
        "results": "{n} stories", "join_h": "Buzzkit on WhatsApp",
        "join_p": "News from the world and home, straight to your phone. Free.", "join_btn": "Join",
        "about": "World and home news in English.",
        "legal": "Headlines and short snippets link to the publisher.<br>Own posts are written by Buzzkit.",
        "pitch": "Pitch a story", "updated": "Updated", "empty": "No stories yet.",
    },
    "sw": {
        "other": "en", "other_name": "English", "all": "Zote", "search": "Tafuta",
        "cats": "Makundi", "hero": "Soma ya asubuhi", "recent": "Habari za hivi karibuni",
        "desk": "Kutoka kwetu", "more": "Habari zaidi", "none": "Hakuna habari zilizopatikana.",
        "results": "Habari {n}", "join_h": "Buzzkit kwenye WhatsApp",
        "join_p": "Habari za dunia na nyumbani, moja kwa moja kwenye simu yako. Bure.", "join_btn": "Jiunge",
        "about": "Habari za dunia na nyumbani kwa Kiswahili.",
        "legal": "Vichwa vya habari na vifupisho vinaelekeza kwa mchapishaji.<br>Makala zetu zimeandikwa na Buzzkit.",
        "pitch": "Tuma habari", "updated": "Imesasishwa", "empty": "Bado hakuna habari.",
    },
}


def month_short(dt, lang):
    return (SW_MONTHS_SHORT if lang == "sw" else EN_MONTHS_SHORT)[dt.month - 1]


def stamp(s):
    t = s["when"].astimezone(EAT)
    return f"{t.day:02d} {month_short(t, s['lang'])}, {t:%H:%M}"


def cat_label(cat, lang):
    return CAT_SW.get(cat, cat) if lang == "sw" else cat


def tags(s):
    return f'<span class="tags">{e(cat_label(s["cat"], s["lang"]))} <i>•</i> {e(s["source"])}</span>'


def head(s, level="h3"):
    t = e(s["title"])
    if s["url"]:
        t = f'<a href="{e(s["url"], quote=True)}" target="_blank" rel="noopener noreferrer">{t}</a>'
    return f"<{level}>{t}</{level}>"


def attrs(s):
    return f'data-lang="{s["lang"]}" data-cat="{e(s["cat"], quote=True)}"'


def hero(s, lang):
    img = f'<img src="{e(s["image"], quote=True)}" alt="" loading="lazy">' if s["image"] else ""
    deck = f'<p class="deck">{e(s["summary"])}</p>' if s["summary"] else ""
    return (f'<section class="hero"><div class="label">{e(TXT[lang]["hero"])}</div>'
            f'{head(s, "h2")}{deck}<div class="when">{tags(s)} <span>{stamp(s)} EAT</span></div>{img}</section>')


def row(s):
    return f'<li {attrs(s)}>{tags(s)}{head(s)}<span class="when">{stamp(s)} EAT</span></li>'


def tile(s):
    img = f'<img src="{e(s["image"], quote=True)}" alt="" loading="lazy">' if s["image"] else ""
    deck = f'<p>{e(s["summary"])}</p>' if s["summary"] else ""
    return f'<article class="tile" {attrs(s)}>{img}{tags(s)}{head(s)}{deck}<span class="when">{stamp(s)} EAT</span></article>'


def mini(s):
    return f'<li {attrs(s)}>{head(s, "h4")}<span class="when">{e(s["source"])} · {stamp(s)}</span></li>'


def date_line(lang):
    n = datetime.now(EAT)
    if lang == "sw":
        return f"{SW_DAYS[n.weekday()]}, {n.day} {SW_MONTHS[n.month - 1]} {n.year}"
    return f"{EN_DAYS[n.weekday()]}, {EN_MONTHS[n.month - 1]} {n.day}, {n.year}"


def fill(template, vals):
    """Replace __NAME__ markers in one pass, so story text can never be mistaken for a marker."""
    return re.sub(r"__([A-Z_]+?)__", lambda m: vals.get(m.group(1), m.group(0)), template)


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Buzzkit</title>
<meta name="description" content="We cover the news of the world and home. Habari za dunia na nyumbani.">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;700;800&family=IBM+Plex+Mono:wght@500&family=Public+Sans:ital,wght@0,400;0,600;1,400&display=swap">
<noscript><style>.chooser{display:none!important}.site{display:block!important}</style></noscript>
<style>
:root{--bg:#fff;--ink:#101820;--muted:#5B6773;--line:#E1E6EB;--bar:#0E1B2B;--bar-ink:#fff;--accent:#1F4FD8;--soft:#F3F6F9;--sw:#0B6B5E;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#0B1118;--ink:#E8EEF4;--muted:#9AA9B7;--line:#222E3A;--bar:#050A10;--bar-ink:#fff;--accent:#8FB0FF;--soft:#121B25;--sw:#59D6C2;color-scheme:dark}}
*{box-sizing:border-box}
[hidden]{display:none!important}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 'Public Sans',system-ui,sans-serif}
a{color:inherit}a:focus-visible,button:focus-visible,input:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
.in{max-width:1080px;margin:0 auto;padding:0 max(16px,env(safe-area-inset-left)) 0 max(16px,env(safe-area-inset-right))}
.site{display:none}
body[data-view=en] .site[data-lang=en],body[data-view=sw] .site[data-lang=sw]{display:block}
.chooser{display:none;min-height:100vh;min-height:100dvh;align-items:center;background:var(--bar);color:var(--bar-ink)}
body[data-view=choose] .chooser{display:flex}
.chooser .in{width:100%;padding-block:40px;display:flex;flex-direction:column;gap:18px}
.chooser .brand{font-size:34px}
.chooser h1{margin:0;font:800 clamp(28px,6vw,48px)/1.1 Archivo,sans-serif;letter-spacing:-.02em;text-wrap:balance}
.chooser p{margin:0;color:#B7C3D0;max-width:52ch}
.choices{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr));gap:16px;max-width:640px;margin-top:6px}
.choice{display:flex;flex-direction:column;gap:6px;padding:22px;border:2px solid #33465c;border-radius:8px;color:var(--bar-ink);text-decoration:none}
.choice b{font:800 26px Archivo,sans-serif}
.choice span{color:#B7C3D0;font-size:15px}
.choice:hover,.choice:focus-visible{border-color:#fff;background:#13243a}
.top{background:var(--bar);color:var(--bar-ink)}
.top .in{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px 20px;padding-block:14px}
.brand{font:800 26px/1 Archivo,'Arial Narrow',sans-serif;letter-spacing:-.02em;text-transform:uppercase;text-decoration:none}
.tools{display:flex;flex-wrap:wrap;align-items:center;gap:10px 12px}
.top input{min-height:40px;width:min(260px,100%);padding:0 12px;border:1px solid #33465c;border-radius:4px;background:transparent;color:var(--bar-ink);font:inherit}
.top input::placeholder{color:#8FA0B3}
.switch{display:inline-flex;align-items:center;min-height:40px;padding:0 16px;border:1px solid #5A708A;border-radius:999px;color:var(--bar-ink);font:700 13px Archivo,sans-serif;letter-spacing:.04em;text-decoration:none}
.switch:hover{background:#1B2B40}
.cats{border-bottom:1px solid var(--line);background:var(--bg);position:sticky;top:0;z-index:5}
.cats .in{display:flex;gap:4px;overflow-x:auto;scrollbar-width:thin}
.cat{flex:none;min-height:46px;padding:0 14px;border:0;border-bottom:3px solid transparent;background:none;color:var(--muted);font:700 13px Archivo,sans-serif;letter-spacing:.06em;text-transform:uppercase;cursor:pointer}
.cat[aria-pressed=true]{color:var(--ink);border-bottom-color:var(--accent)}
.datebar{padding-block:12px;color:var(--muted);font:500 12px 'IBM Plex Mono',monospace;letter-spacing:.03em;text-transform:uppercase}
main{padding-bottom:40px}
.tags{font:500 11px 'IBM Plex Mono',monospace;letter-spacing:.06em;text-transform:uppercase;color:var(--accent)}
.tags i{font-style:normal;color:var(--muted);padding:0 2px}
.when{font:400 12.5px 'Public Sans',sans-serif;color:var(--muted)}
a{text-decoration:none}h2 a:hover,h3 a:hover,h4 a:hover{text-decoration:underline;text-decoration-thickness:2px}
.hero{padding-block:28px 32px;border-bottom:1px solid var(--line);display:flex;flex-direction:column;gap:12px}
.label{font:700 12px Archivo,sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--accent)}
.hero h2{margin:0;font:800 clamp(30px,5vw,52px)/1.06 Archivo,sans-serif;letter-spacing:-.025em;max-width:22ch;text-wrap:balance}
.deck{margin:0;font-size:19px;color:var(--muted);max-width:62ch;white-space:pre-line}
.hero img,.tile img{width:100%;max-width:100%;height:auto;aspect-ratio:16/9;object-fit:cover;border-radius:4px;background:var(--soft)}
.sec{padding-top:30px}
.sec>h5{margin:0 0 6px;font:800 13px Archivo,sans-serif;letter-spacing:.14em;text-transform:uppercase;padding-bottom:10px;border-bottom:2px solid var(--ink)}
ul.list{list-style:none;margin:0;padding:0}
ul.list>li{display:flex;flex-direction:column;gap:4px;padding:16px 0;border-bottom:1px solid var(--line)}
ul.list h3{margin:0;font:700 21px/1.25 Archivo,sans-serif;letter-spacing:-.01em;text-wrap:balance}
.two{display:grid;grid-template-columns:minmax(0,1fr);gap:32px}
@media(min-width:900px){.two{grid-template-columns:minmax(0,2fr) minmax(0,1fr);gap:48px}}
.join{background:var(--soft);border:1px solid var(--line);border-radius:6px;padding:22px;display:flex;flex-direction:column;gap:10px;align-self:start}
.join h5{margin:0;font:800 20px Archivo,sans-serif}.join p{margin:0;color:var(--muted);font-size:15px}
.btn{display:inline-flex;align-items:center;min-height:46px;padding:0 20px;border-radius:4px;background:var(--accent);color:var(--bg);font:700 15px Archivo,sans-serif;width:fit-content}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,300px),1fr));gap:24px;padding-top:18px}
.tile{display:flex;flex-direction:column;gap:8px;min-width:0}
.tile h3{margin:0;font:700 20px/1.25 Archivo,sans-serif;text-wrap:balance}.tile p{margin:0;color:var(--muted);font-size:15px;white-space:pre-line}
ul.minis{list-style:none;margin:0;padding:0}
ul.minis li{display:flex;flex-direction:column;gap:2px;padding:12px 0;border-bottom:1px solid var(--line)}
ul.minis h4{margin:0;font:600 16px/1.35 'Public Sans',sans-serif}
.none{padding:32px 0;color:var(--muted)}
footer{background:var(--bar);color:#B7C3D0;margin-top:20px}
footer .in{display:flex;flex-wrap:wrap;justify-content:space-between;gap:12px 32px;padding-block:28px;font-size:13px}
footer b{display:block;color:#fff;font:800 20px Archivo,sans-serif;text-transform:uppercase;margin-bottom:4px}
footer a{color:#fff;text-decoration:underline}
</style>
</head>
<body>
<section class="chooser" aria-labelledby="ct"><div class="in">
<div class="brand">Buzzkit</div>
<h1 id="ct">Choose your language<br>Chagua lugha</h1>
<p>Read the news in the language you prefer. · Soma habari kwa lugha unayopenda.</p>
<div class="choices">
<a class="choice" href="#en" lang="en"><b>English</b><span>World and home news</span></a>
<a class="choice" href="#sw" lang="sw"><b>Kiswahili</b><span>Habari za dunia na nyumbani</span></a>
</div>
</div></section>
__SITES__
<script>
var DATA=__DATA__;
(function(){
var KEY='buzzkit-lang';
function saved(){try{return localStorage.getItem(KEY)}catch(x){return null}}
function save(v){try{localStorage.setItem(KEY,v)}catch(x){}}
function view(){
  var h=location.hash.replace('#','');
  if(h==='en'||h==='sw'){save(h);return h}
  var s=saved();
  return (s==='en'||s==='sw')?s:'choose';
}
function show(){
  var v=view();
  document.body.setAttribute('data-view',v);
  if(v!=='choose')document.documentElement.lang=v;
  window.scrollTo(0,0);
}
window.addEventListener('hashchange',show);
show();
[].forEach.call(document.querySelectorAll('.site'),function(root){
  var lg=root.getAttribute('data-lang'),cat='all',q='';
  var home=root.querySelector('.home'),res=root.querySelector('.results'),list=root.querySelector('.rlist'),
      none=root.querySelector('.rnone'),rt=root.querySelector('.rtitle'),input=root.querySelector('.q');
  function build(){
    var f=DATA.filter(function(s){
      return s.l===lg&&(cat==='all'||s.c===cat)&&(!q||(s.t+' '+s.x+' '+s.s).toLowerCase().indexOf(q)>=0)});
    list.replaceChildren();
    f.forEach(function(s){
      var li=document.createElement('li'),tg=document.createElement('span'),h=document.createElement('h3'),w=document.createElement('span');
      tg.className='tags';tg.textContent=s.cl+' • '+s.s;
      if(s.u){var a=document.createElement('a');a.href=s.u;a.target='_blank';a.rel='noopener noreferrer';a.textContent=s.t;h.appendChild(a)}else h.textContent=s.t;
      w.className='when';w.textContent=s.d+' EAT';
      li.appendChild(tg);li.appendChild(h);
      if(s.x){var p=document.createElement('p');p.className='deck';p.style.fontSize='16px';p.textContent=s.x;li.appendChild(p)}
      li.appendChild(w);list.appendChild(li);});
    none.hidden=f.length>0;
    rt.textContent=root.getAttribute('data-rt').replace('{n}',f.length);
  }
  function apply(){
    var on=cat!=='all'||q!=='';
    home.hidden=on;res.hidden=!on;
    if(on)build();
  }
  [].forEach.call(root.querySelectorAll('.cat'),function(b){b.addEventListener('click',function(){
    cat=b.getAttribute('data-cat');
    [].forEach.call(root.querySelectorAll('.cat'),function(x){x.setAttribute('aria-pressed',String(x===b))});
    apply()})});
  input.addEventListener('input',function(ev){q=ev.target.value.trim().toLowerCase();apply()});
});
})();
</script>
</body>
</html>
"""

SITE = """<div class="site" data-lang="__LANG__" data-rt="__RT__">
<header class="top"><div class="in">
<a class="brand" href="./">Buzzkit</a>
<span class="tools"><input class="q" type="search" placeholder="__SEARCH__" aria-label="__SEARCH__" autocomplete="off"><a class="switch" href="#__OTHER__" lang="__OTHER__">__OTHERNAME__</a></span>
</div></header>
<nav class="cats" aria-label="__CATSLABEL__"><div class="in">__CATS__</div></nav>
<div class="in">
<div class="datebar">__DATE__</div>
<main>
<div class="home">
__HERO__
<div class="two">
<section class="sec"><h5>__RECENTH__</h5><ul class="list">__RECENT__</ul></section>
__JOIN__
</div>
__TILES__
__MORESEC__
</div>
<div class="results" hidden><section class="sec"><h5 class="rtitle"></h5><ul class="list rlist"></ul><p class="none rnone" hidden>__NONE__</p></section></div>
</main>
</div>
<footer><div class="in">
<div><b>Buzzkit</b>__ABOUT__<br>© __YEAR__ Buzzkit | Dar es Salaam<br>__UPDATEDLABEL__ __UPDATED__ EAT</div>
<div>__LEGAL____CONTACT__</div>
</div></footer>
</div>"""


def render_site(stories, lang, now):
    """One complete page (menu, stories, footer) holding only stories written in `lang`."""
    t = TXT[lang]
    mine = [s for s in stories if s["lang"] == lang]
    lead = next((s for s in mine if s["own"] and s["pinned"]), mine[0] if mine else None)
    rest = [s for s in mine if s is not lead]
    recent, rest = rest[:10], rest[10:]
    desk = [s for s in rest if s["own"]][:3]
    more = [s for s in rest if s not in desk][:40]

    cats = sorted({s["cat"] for s in mine},
                  key=lambda c: (CAT_ORDER.index(c) if c in CAT_ORDER else 9, c))
    cat_btns = f'<button type="button" class="cat" data-cat="all" aria-pressed="true">{e(t["all"])}</button>' + "".join(
        f'<button type="button" class="cat" data-cat="{e(c, quote=True)}" aria-pressed="false">{e(cat_label(c, lang))}</button>'
        for c in cats)

    join = ""
    if CHANNEL_URL.startswith("https://"):
        join = (f'<aside class="join"><h5>{e(t["join_h"])}</h5><p>{e(t["join_p"])}</p>'
                f'<a class="btn" href="{e(CHANNEL_URL, quote=True)}" target="_blank" rel="noopener noreferrer">{e(t["join_btn"])}</a></aside>')
    tiles = (f'<section class="sec"><h5>{e(t["desk"])}</h5><div class="tiles">'
             + "".join(tile(s) for s in desk) + "</div></section>") if desk else ""
    more_sec = (f'<section class="sec"><h5>{e(t["more"])}</h5><ul class="minis">'
                + "".join(mini(s) for s in more) + "</ul></section>") if more else ""
    contact = (f'<br>{e(t["pitch"])}: <a href="mailto:{e(CONTACT_EMAIL, quote=True)}">{e(CONTACT_EMAIL)}</a>'
               if CONTACT_EMAIL else "")
    return fill(SITE, {
        "LANG": lang, "RT": e(t["results"], quote=True), "SEARCH": e(t["search"], quote=True),
        "OTHER": t["other"], "OTHERNAME": e(t["other_name"]), "CATSLABEL": e(t["cats"], quote=True),
        "CATS": cat_btns, "DATE": e(date_line(lang)),
        "HERO": hero(lead, lang) if lead else f'<p class="none">{e(t["empty"])}</p>',
        "RECENTH": e(t["recent"]), "RECENT": "".join(row(s) for s in recent),
        "JOIN": join, "TILES": tiles, "MORESEC": more_sec, "NONE": e(t["none"]),
        "ABOUT": e(t["about"]), "YEAR": str(now.year), "UPDATEDLABEL": e(t["updated"]),
        "UPDATED": f"{now.day:02d} {month_short(now, lang)} {now:%H:%M}",
        "LEGAL": t["legal"], "CONTACT": contact,
    })


def main(out="index.html"):
    hide = read_hide()
    stories, seen = [], set()
    cutoff = datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)
    for source, lang, url, cat in FEEDS:
        try:
            items = parse_feed(fetch(url), source, lang)
        except Exception as ex:  # one broken feed must not stop the build
            print(f"skipped {source}: {ex}", file=sys.stderr)
            continue
        added = 0
        for s in items:
            if s["url"] in seen or s["when"] < cutoff or is_hidden(s, hide):
                continue
            s["cat"] = cat
            seen.add(s["url"])
            stories.append(s)
            added += 1
        print(f"{source}: {added} stories")
    own = [s for s in read_posts() if not is_hidden(s, hide)]
    stories = sorted(stories + own, key=lambda s: s["when"], reverse=True)[:200]

    now = datetime.now(EAT)
    sites = "\n".join(render_site(stories, lang, now) for lang in ("en", "sw"))
    data = [{"t": s["title"], "x": s["summary"], "u": s["url"], "s": s["source"], "c": s["cat"],
             "cl": cat_label(s["cat"], s["lang"]), "l": s["lang"], "d": stamp(s)} for s in stories]
    data_js = (json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
               .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))
    page = fill(TEMPLATE, {"SITES": sites, "DATA": data_js})
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(page)
    counts = {lang: sum(1 for s in stories if s["lang"] == lang) for lang in ("en", "sw")}
    print(f"Wrote {len(stories)} stories to {out} (English {counts['en']}, Kiswahili {counts['sw']})")


if __name__ == "__main__":
    main()
