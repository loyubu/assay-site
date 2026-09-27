#!/usr/bin/env python3
"""Checks the public site: its data, its boundary, and its page.

Runs on every push and pull request (see workflows/check-site.yml), and
locally with `python3 .github/check_site.py [repo root]`. Exits 1 if any
check fails, listing each failure.

It runs after a push lands, so it flags a problem rather than preventing
one. The allowlist in the private build is still the real guard; this is
the second fence at the boundary.
"""
import html as htmllib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
failures = []


def fail(msg):
    failures.append(msg)
    print("FAIL " + msg)


def ok(msg):
    print("ok   " + msg)


page = (ROOT / "index.html").read_text(encoding="utf-8")
readme = (ROOT / "README.md").read_text(encoding="utf-8")
DATA_BLOCK = re.compile(r'<script id="data" type="application/json">(.*?)</script>', re.S)


# ---------- the data parses ----------

def load(label, text):
    try:
        doc = json.loads(text)
        ok(f"{label} parses")
        return doc
    except json.JSONDecodeError as e:
        fail(f"{label} is not valid JSON: {e}")
        return {}

blocks = DATA_BLOCK.findall(page)
if len(blocks) != 1:
    fail(f"index.html should hold exactly one data block, found {len(blocks)}")
data = load("the page's inline data", blocks[0]) if blocks else {}
stats = load("stats.json", (ROOT / "stats.json").read_text(encoding="utf-8"))


# ---------- the page has what it draws ----------

REQUIRED = ["generated_at", "window", "systems", "systems_daily", "signflip",
            "faithfulness", "criteria", "cost", "pyramid"]
REQUIRED_PER_SYSTEM = ["name", "display", "trades", "expectancy_r", "t_stat",
                       "by_spread", "verdict", "adequacy", "equity_curve"]
missing = [k for k in REQUIRED if k not in data]
for table in ("systems", "systems_daily"):
    for s in data.get(table) or []:
        gaps = [k for k in REQUIRED_PER_SYSTEM if k not in s]
        if gaps:
            missing.append(f"{table}/{s.get('display') or s.get('name')}: {', '.join(gaps)}")
if missing:
    fail("the page's data is missing: " + "; ".join(missing))
else:
    ok("the page's data has every field the page draws")


# ---------- nothing crosses that must not ----------
# README, "What crosses the boundary": never an account balance or
# identifier, open positions, profit and loss in any currency, broker order
# or trade identifiers, or the clock time of any individual decision.
# USD appears only as the AI's own running cost (cost.*_usd), which is
# published on purpose.

FORBIDDEN_KEY = re.compile(
    r"balance|account|acct|broker|order|ticket|position|pnl|p_?and_?l|realis|realiz"
    r"|profit_(?!factor)|_(gbp|eur|jpy|chf|aud|cad|nzd)\b|timestamp|clock|_time\b|^time$|_at$",
    re.I)
ALLOWED_KEYS = {"generated_at"}
CLOCK_TIME = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
CURRENCY = re.compile(r"[£€¥]|\$\s?\d")


def walk(node, path, found):
    if isinstance(node, dict):
        for k, v in node.items():
            here = f"{path}.{k}" if path else k
            if k not in ALLOWED_KEYS and FORBIDDEN_KEY.search(k):
                found.append(f"field {here}")
            if k not in ALLOWED_KEYS:
                walk(v, here, found)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            walk(v, f"{path}[{i}]", found)
    elif isinstance(node, str):
        if CLOCK_TIME.search(node):
            found.append(f"a clock time in {path}")
        if CURRENCY.search(node):
            found.append(f"a currency amount in {path}")

for label, doc in (("the page's inline data", data), ("stats.json", stats)):
    found = []
    walk(doc, "", found)
    if found:
        fail(f"{label} holds what must never be published: " + "; ".join(found[:10]))
    else:
        ok(f"{label} holds nothing from the never-published list")


# ---------- nicknames only ----------
# The data still carries the build's internal ids beside the nicknames;
# everywhere else, on the page and in the README, rule sets go by nickname.

outside_data = DATA_BLOCK.sub("", page)
ids = sorted({s["name"] for t in ("systems", "systems_daily") for s in data.get(t) or [] if s.get("name")})
leaks = [i for i in ids
         for where, text in (("index.html", outside_data), ("README.md", readme))
         if re.search(r"(?<![\w-])" + re.escape(i) + r"(?![\w-])", text, re.I)]
if leaks:
    fail("an internal id appears outside the data: " + ", ".join(sorted(set(leaks))))
else:
    ok(f"none of the {len(ids)} internal ids appears outside the data")


# ---------- every column definition exists ----------

glossary = re.search(r'<section id="glossary">(.*?)</section>', page, re.S)
defined = {re.sub(r"\s+", " ", htmllib.unescape(t)).strip()
           for t in re.findall(r"<dt>(.*?)</dt>", glossary.group(1) if glossary else "", re.S)}
asked = set(re.findall(r'data-term="([^"]+)"', page))
undefined = sorted(asked - defined)
if undefined:
    fail("column headings name terms the glossary lacks: " + ", ".join(undefined))
else:
    ok(f"all {len(asked)} column-heading terms are in the glossary")


# ---------- every file the page asks for is here ----------

local = set(re.findall(r'(?:url\(|href=)"(fonts/[^"]+)"', page))
absent = sorted(f for f in local if not (ROOT / f).is_file())
if absent:
    fail("the page asks for files that aren't in the repo: " + ", ".join(absent))
else:
    ok(f"all {len(local)} font files the page asks for are present")


# ---------- the page's scripts parse ----------

scripts = [s for s in re.findall(r"<script(?![^>]*application/json)[^>]*>(.*?)</script>", page, re.S) if s.strip()]
node = shutil.which("node")
if not node:
    print(f"skip the page's {len(scripts)} scripts: node isn't installed here")
else:
    broken = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, body in enumerate(scripts):
            f = Path(tmp) / f"script{i}.js"
            f.write_text(body, encoding="utf-8")
            r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
            if r.returncode:
                lines = r.stderr.strip().splitlines()
                why = next((l for l in lines if "Error" in l), "syntax error")
                where = next((l.strip() for l in lines if re.match(r".*script\d+\.js:\d+", l)), "")
                line = re.search(r":(\d+)$", where)
                broken.append(f"script {i + 1}" + (f", line {line.group(1)}" if line else "") + f": {why}")
    if broken:
        fail("the page's script doesn't parse: " + "; ".join(broken))
    else:
        ok(f"the page's {len(scripts)} scripts parse")


print()
if failures:
    print(f"{len(failures)} check(s) failed")
    sys.exit(1)
print("all checks passed")
