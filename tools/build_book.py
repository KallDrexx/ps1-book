#!/usr/bin/env python3
"""Build the book as a PDF and an EPUB.

    tools/build-book.sh REVISION          # e.g. tools/build-book.sh 3

Writes output/Programming-PS1-Games-r<REVISION>.pdf and .epub.

What goes in: the introduction from README.md (prerequisites, setup, how to work
through a chapter), every part introduction, every chapter README plus its quiz, and
appendices A-G. Summary.md (the authoring spec) is left out. Links between chapters
and appendices become internal links; links to files that are not in the book
(starter code, tools) become plain text.

Needs: Python 3 with `markdown-it-py` (in tools/requirements.txt) and, for the PDF,
Chromium or Google Chrome (headless). Pass --no-pdf or --no-epub to skip one.
"""
import argparse
import datetime
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path
from posixpath import normpath, join as pjoin, dirname as pdirname

try:
    from markdown_it import MarkdownIt
except ImportError:
    sys.exit("build_book: missing 'markdown-it-py'. Run: pip install -r tools/requirements.txt "
             "(or tools/setup.sh).")

ROOT = Path(__file__).resolve().parent.parent
TITLE = "Programming PS1 Games"
FILE_STEM = "Programming-PS1-Games"

# README.md sections that belong in the book (the rest is repository housekeeping).
ABOUT_SECTIONS = {"Prerequisites", "Setup", "Working through a chapter"}

CSS_COMMON = """
html { font-family: "Charter", "Georgia", "DejaVu Serif", serif; line-height: 1.45; }
body { margin: 0; color: #1a1a1a; }
h1, h2, h3, h4, h5, h6 { font-family: "Helvetica Neue", "Liberation Sans", "DejaVu Sans", sans-serif;
  line-height: 1.2; margin: 1.4em 0 .5em; }
h1 { font-size: 2em; } h2 { font-size: 1.6em; } h3 { font-size: 1.25em; } h4 { font-size: 1.1em; }
h5, h6 { font-size: 1em; }
code, pre, kbd { font-family: "DejaVu Sans Mono", "Liberation Mono", monospace; font-size: .85em; }
code { background: #f1f1f1; padding: 0 .2em; border-radius: 2px; overflow-wrap: anywhere; }
pre { background: #f6f6f6; border: 1px solid #ddd; padding: .6em .8em; white-space: pre-wrap;
  overflow-wrap: anywhere; line-height: 1.3; }
pre code { background: none; padding: 0; font-size: 1em; }
table { border-collapse: collapse; margin: 1em 0; font-size: .88em; }
th, td { border: 1px solid #bbb; padding: .25em .5em; vertical-align: top; text-align: left; }
th { background: #eee; }
blockquote { margin: 1em 0; padding: .1em 1em; border-left: 4px solid #ccc; color: #444; }
a { color: #0b4f9c; text-decoration: none; }
.unlinked { }
nav.toc ul { list-style: none; padding-left: 1.2em; margin: .2em 0; }
nav.toc > ul { padding-left: 0; }
nav.toc li.part { margin-top: .9em; font-weight: bold; font-family: "Helvetica Neue", "Liberation Sans", sans-serif; }
nav.toc li.part li { font-weight: normal; font-family: inherit; margin-top: .1em; }
.titlepage { text-align: center; margin-top: 28%; }
.titlepage h1 { font-size: 3em; margin-bottom: 1.2em; }
.titlepage p { font-size: 1.3em; margin: .4em 0; }
"""

CSS_PDF = """
@page { size: Letter; margin: 0.9in 0.8in 1in 0.8in;
  @bottom-center { content: counter(page); font: 9pt "Helvetica Neue", "Liberation Sans", sans-serif; color: #555; } }
@page :first { @bottom-center { content: none; } }
html { font-size: 10.5pt; }
section.chapter, section.part, section.divider { break-before: page; }
section.titlepage-wrap, nav.toc-wrap { break-after: page; }
h1, h2, h3, h4 { break-after: avoid; }
table, figure { break-inside: avoid; }
tr { break-inside: avoid; }
section.part h1 { font-size: 2.4em; margin-top: 30%; }
"""

CSS_EPUB = """
body { padding: 0 .3em; }
pre { font-size: .8em; }
"""


# ----------------------------------------------------------------------------- model
class Doc:
    def __init__(self, docid, path, kind, source=None, title=None):
        self.id = docid          # unique prefix for anchors, e.g. "ch12"
        self.path = path         # repo-relative posix path of the markdown source (for link lookup)
        self.kind = kind         # about | part | chapter | appendix
        self.source = source     # markdown text
        self.title = title
        self.extra_paths = []    # other files folded into this doc (the quiz)
        self.tokens = None
        self.html = None


def read(path):
    return flatten_details((ROOT / path).read_text(encoding="utf-8"))


def flatten_details(text):
    """Quiz answers are <details> blocks; print and e-readers do not expand those and
    Markdown does not parse inside raw HTML, so turn them into a labelled paragraph."""
    text = re.sub(r"<details>\s*<summary>(.*?)</summary>\s*", lambda m: f"\n**{m.group(1)}:** ", text)
    return re.sub(r"\s*</details>", "\n", text)


def keep_about(text):
    """Return README.md reduced to the sections that belong in the book."""
    out, current, keep = [], None, True
    for line in text.splitlines():
        if line.startswith("# "):
            out.append("# About This Book")
            continue
        m = re.match(r"## (.+?)\s*$", line)
        if m:
            current = m.group(1)
            keep = current in ABOUT_SECTIONS
        elif current is None and line.startswith("See [`Summary.md`"):
            continue
        if keep:
            out.append(line)
    return "\n".join(out) + "\n"


def collect_docs():
    docs = [Doc("about", "README.md", "about", keep_about(read("README.md")), "About This Book")]
    for part_dir in sorted((ROOT / "parts").glob("part-*")):
        pn = part_dir.name.split("-")[1]
        rel = part_dir.relative_to(ROOT).as_posix()
        docs.append(Doc("p" + pn, f"{rel}/README.md", "part", read(f"{rel}/README.md")))
        for ch_dir in sorted(part_dir.glob("ch*")):
            cn = ch_dir.name.split("-")[0]
            crel = ch_dir.relative_to(ROOT).as_posix()
            d = Doc(cn, f"{crel}/README.md", "chapter", read(f"{crel}/README.md"))
            quiz = ch_dir / "quiz.md"
            if quiz.exists():
                q = Doc(cn + "-quiz", f"{crel}/quiz.md", "quiz", read(f"{crel}/quiz.md"))
                d.quiz = q
            else:
                d.quiz = None
            docs.append(d)
    for f in sorted((ROOT / "appendices").glob("[A-G]-*.md")):
        rel = f.relative_to(ROOT).as_posix()
        docs.append(Doc("app" + f.name[0], rel, "appendix", read(rel)))
    return docs


# ----------------------------------------------------------------------------- markdown
def make_md():
    md = MarkdownIt("commonmark", {"html": True, "xhtmlOut": True, "typographer": False})
    md.enable("table").enable("strikethrough")
    return md


def github_slug(text):
    s = text.strip().lower()
    s = re.sub(r"[^\w\- ]", "", s, flags=re.UNICODE)
    return s.replace(" ", "-")


def inline_text(tok):
    parts = []
    for c in tok.children or []:
        if c.type in ("text", "code_inline"):
            parts.append(c.content)
        elif c.type in ("softbreak", "hardbreak"):
            parts.append(" ")
    return "".join(parts)


def assign_ids(doc, level_shift):
    """Give every heading an id (H1 -> doc id) and shift heading levels for the book."""
    seen = {}
    doc.ids = set()
    toks = doc.tokens
    for i, t in enumerate(toks):
        if t.type != "heading_open":
            continue
        level = int(t.tag[1])
        text = inline_text(toks[i + 1])
        if level == 1 and doc.title is None:
            doc.title = text
        if level == 1:
            hid = doc.id
        else:
            slug = github_slug(text)
            n = seen.get(slug, 0)
            seen[slug] = n + 1
            hid = f"{doc.id}--{slug}" + (f"-{n}" if n else "")
        t.attrSet("id", hid)
        doc.ids.add(hid)
        new = min(level + level_shift, 6)
        t.tag = f"h{new}"
        # find the matching close token
        for j in range(i + 1, len(toks)):
            if toks[j].type == "heading_close":
                toks[j].tag = f"h{new}"
                break


SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def rewrite_links(doc, by_path, all_ids, warnings):
    base = pdirname(doc.link_base)
    for t in doc.tokens:
        if t.type != "inline":
            continue
        open_stack = []
        for c in t.children:
            if c.type == "link_open":
                href = c.attrGet("href") or ""
                new = resolve(href, base, doc, by_path, all_ids, warnings)
                if new is None:
                    c.tag = "span"
                    c.attrs = {"class": "unlinked"}
                    open_stack.append(True)
                else:
                    c.attrSet("href", new)
                    open_stack.append(False)
            elif c.type == "link_close":
                if open_stack.pop():
                    c.tag = "span"


def resolve(href, base, doc, by_path, all_ids, warnings):
    """Return the in-book anchor (e.g. '#ch12--foo'), an external URL, or None to unlink."""
    if SCHEME.match(href):
        return href
    path, _, frag = href.partition("#")
    if not path:
        target = doc
        base_id = doc.id
    else:
        full = normpath(pjoin(base, path))
        target = by_path.get(full)
        if target is None:
            return None
        base_id = target.id
    if not frag:
        return "#" + base_id
    anchor = f"{base_id}--{github_slug(frag)}"
    if anchor in all_ids:
        return "#" + anchor
    warnings.append(f"{doc.path}: anchor not found for '{href}' -> falling back to the document start")
    return "#" + base_id


def build_docs(docs):
    md = make_md()
    shifts = {"about": 0, "part": 0, "chapter": 1, "quiz": 2, "appendix": 1}
    for d in docs:
        d.link_base = d.path
        d.tokens = md.parse(d.source)
        assign_ids(d, shifts[d.kind])
        if getattr(d, "quiz", None):
            q = d.quiz
            q.link_base = q.path
            q.tokens = md.parse(q.source)
            assign_ids(q, shifts["quiz"])
    # the book's headings: about/part sections sit one level below their H1, chapters two
    for d in docs:
        if d.kind == "part":
            demote_sub(d, 2)
    by_path = {}
    all_ids = set()
    flat = []
    for d in docs:
        flat.append(d)
        if getattr(d, "quiz", None):
            flat.append(d.quiz)
    for d in flat:
        by_path[d.path] = d
        all_ids |= d.ids
    warnings = []
    for d in flat:
        rewrite_links(d, by_path, all_ids, warnings)
    for d in flat:
        d.html = md.renderer.render(d.tokens, md.options, {})
    return flat, warnings


def demote_sub(doc, shift):
    """Part introductions: keep the part title as <h1>, push the rest below chapter level."""
    toks = doc.tokens
    for i, t in enumerate(toks):
        if t.type == "heading_open" and t.tag != "h1":
            new = min(int(t.tag[1]) + shift - 1, 6)
            t.tag = f"h{new}"
            for j in range(i + 1, len(toks)):
                if toks[j].type == "heading_close":
                    toks[j].tag = f"h{new}"
                    break


# ----------------------------------------------------------------------------- html assembly
def toc_entries(docs):
    """[(part_title, part_id, [(title, id), ...])] plus the front matter and appendices."""
    entries = []
    cur = None
    for d in docs:
        if d.kind == "quiz":
            continue
        if d.kind == "about":
            entries.append(("front", d.title, d.id, []))
        elif d.kind == "part":
            cur = (d.title, d.id, [])
            entries.append(("part",) + cur)
        elif d.kind == "chapter":
            cur[2].append((d.title, d.id))
        elif d.kind == "appendix":
            if not entries or entries[-1][0] != "appendices":
                entries.append(("appendices", "Appendices", "appendices", []))
            entries[-1][3].append((d.title, d.id))
    return entries


def render_toc(entries, href):
    out = ['<nav class="toc" id="toc" epub:type="toc"><h1>Contents</h1><ul>']
    for kind, title, tid, kids in entries:
        out.append(f'<li class="part"><a href="{href(tid)}">{html.escape(title)}</a>')
        if kids:
            out.append("<ul>")
            for ctitle, cid in kids:
                out.append(f'<li><a href="{href(cid)}">{html.escape(ctitle)}</a></li>')
            out.append("</ul>")
        out.append("</li>")
    out.append("</ul></nav>")
    return "\n".join(out)


def titlepage(revision, date_text):
    return (f'<section class="titlepage-wrap"><div class="titlepage" id="titlepage">'
            f"<h1>{html.escape(TITLE)}</h1>"
            f"<p>Revision {html.escape(revision)}</p>"
            f"<p>{html.escape(date_text)}</p></div></section>")


def section_html(d):
    cls = {"about": "chapter", "part": "part", "chapter": "chapter", "appendix": "chapter"}[d.kind]
    body = d.html
    if getattr(d, "quiz", None):
        body += f'\n<div class="quiz">{d.quiz.html}</div>'
    return f'<section class="{cls}">\n{body}\n</section>'


def appendices_divider():
    return ('<section class="divider" id="appendices"><h1>Appendices</h1>'
            "<p>Reference material for the chapters.</p></section>")


def build_pdf_html(docs, revision, date_text):
    entries = toc_entries(docs)
    parts = [titlepage(revision, date_text),
             '<div class="toc-wrap">' + render_toc(entries, lambda i: "#" + i) + "</div>"]
    inserted = False
    for d in docs:
        if d.kind == "quiz":
            continue
        if d.kind == "appendix" and not inserted:
            parts.append(appendices_divider())
            inserted = True
        parts.append(section_html(d))
    doc = (f'<!DOCTYPE html>\n<html lang="en" xmlns:epub="http://www.idpf.org/2007/ops"><head><meta charset="utf-8">'
           f"<title>{html.escape(TITLE)}</title><style>{CSS_COMMON}{CSS_PDF}</style></head><body>\n"
           + "\n".join(parts) + "\n</body></html>\n")
    return doc


# ----------------------------------------------------------------------------- pdf
def find_chrome():
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    return None


def make_pdf(html_text, out_pdf):
    chrome = find_chrome()
    if not chrome:
        sys.exit("build_book: no Chromium/Chrome found for the PDF (install chromium, or use --no-pdf).")
    with tempfile.TemporaryDirectory(prefix="ps1book-pdf-", dir=str(ROOT / "build")) as tmp:
        src = Path(tmp) / "book.html"
        src.write_text(html_text, encoding="utf-8")
        pdf = Path(tmp) / "book.pdf"
        cmd = [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
               "--generate-pdf-document-outline", "--disable-pdf-tagging", f"--user-data-dir={Path(tmp) / 'profile'}",
               f"--print-to-pdf={pdf}", src.as_uri()]
        try:
            subprocess.run(cmd, check=True, timeout=600, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            sys.exit("build_book: Chromium timed out while printing the PDF.")
        except subprocess.CalledProcessError as e:
            sys.exit(f"build_book: Chromium failed (exit {e.returncode}).")
        if not pdf.exists() or pdf.stat().st_size < 10000:
            sys.exit("build_book: Chromium produced no PDF.")
        shutil.copyfile(pdf, out_pdf)


def add_bookmarks(pdf_path, entries):
    """Chromium's own outline needs the (huge) tagged-PDF structure, so build the sidebar
    bookmarks from the table of contents instead, using the PDF's named destinations."""
    try:
        import pypdf
    except ImportError:
        print("note: pypdf not installed, PDF has no sidebar bookmarks (the contents page still links)",
              file=sys.stderr)
        return
    reader = pypdf.PdfReader(str(pdf_path))
    named = {str(k).lstrip("/"): v for k, v in reader.named_destinations.items()}

    def page_of(anchor):
        dest = named.get(anchor)
        return reader.get_destination_page_number(dest) if dest is not None else None

    writer = pypdf.PdfWriter(clone_from=reader)
    writer.add_outline_item(title="Contents", page_number=1)
    missing = 0
    for _kind, title, tid, kids in entries:
        pg = page_of(tid)
        if pg is None:
            missing += 1
            continue
        parent = writer.add_outline_item(title=title, page_number=pg)
        for ctitle, cid in kids:
            cp = page_of(cid)
            if cp is None:
                missing += 1
            else:
                writer.add_outline_item(title=ctitle, page_number=cp, parent=parent)
    if missing:
        print(f"note: {missing} bookmark target(s) not found in the PDF", file=sys.stderr)
    writer.page_mode = "/UseOutlines"
    writer.add_metadata({"/Title": TITLE})
    with open(pdf_path, "wb") as f:
        writer.write(f)


# ----------------------------------------------------------------------------- epub
def xhtml_page(title, body, extra_css="style.css"):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en" xml:lang="en">'
            f'<head><meta charset="utf-8"/><title>{html.escape(title)}</title>'
            f'<link rel="stylesheet" type="text/css" href="{extra_css}"/></head><body>\n{body}\n</body></html>\n')


def make_epub(docs, revision, date_text, out_epub):
    files = []   # (zip name, bytes, media-type, id, in_spine, properties)
    # which file holds which anchor
    home = {"titlepage": "titlepage.xhtml", "toc": "nav.xhtml", "appendices": "appendices.xhtml"}
    for d in docs:
        if d.kind == "quiz":
            continue
        fname = f"{d.id}.xhtml"
        home[d.id] = fname
        for i in d.ids:
            home[i] = fname
        if getattr(d, "quiz", None):
            home[d.quiz.id] = fname
            for i in d.quiz.ids:
                home[i] = fname

    def href(anchor):
        return f"{home[anchor]}#{anchor}" if anchor not in ("titlepage", "toc") else home[anchor]

    def fix_links(h):
        # in-book links were written as '#anchor'; point them at the file that holds the anchor
        def sub(m):
            a = m.group(1)
            return f'href="{home[a]}#{a}"' if a in home else m.group(0)
        return re.sub(r'href="#([^"]+)"', sub, h)

    entries = toc_entries(docs)
    nav_body = render_toc(entries, lambda i: f"{home[i]}#{i}" if i not in ("appendices",) else "appendices.xhtml")
    spine = []
    pages = {}
    pages["titlepage.xhtml"] = xhtml_page(TITLE, titlepage(revision, date_text).replace('class="titlepage-wrap"', 'class="titlepage-wrap"'))
    pages["nav.xhtml"] = xhtml_page("Contents", nav_body)
    inserted = False
    for d in docs:
        if d.kind == "quiz":
            continue
        if d.kind == "appendix" and not inserted:
            pages["appendices.xhtml"] = xhtml_page("Appendices", appendices_divider())
            inserted = True
        pages[f"{d.id}.xhtml"] = xhtml_page(d.title, fix_links(section_html(d)))
    # well-formedness check: EPUB readers reject broken XHTML
    from xml.dom import minidom
    for name, text in pages.items():
        try:
            minidom.parseString(text.encode("utf-8"))
        except Exception as e:  # noqa: BLE001
            raise SystemExit(f"build_book: {name} is not well-formed XHTML: {e}")

    order = ["titlepage.xhtml", "nav.xhtml"]
    for d in docs:
        if d.kind == "quiz":
            continue
        if d.kind == "appendix" and "appendices.xhtml" not in order:
            order.append("appendices.xhtml")
        order.append(f"{d.id}.xhtml")

    ident = uuid.uuid5(uuid.NAMESPACE_URL, f"ps1-book/{revision}")
    modified = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = ['<item id="css" href="style.css" media-type="text/css"/>']
    for n, name in enumerate(order):
        props = ' properties="nav"' if name == "nav.xhtml" else ""
        manifest.append(f'<item id="i{n}" href="{name}" media-type="application/xhtml+xml"{props}/>')
    spine_xml = "".join(f'<itemref idref="i{n}"/>' for n in range(len(order)))
    opf = ('<?xml version="1.0" encoding="utf-8"?>\n'
           '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="en">'
           '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
           f'<dc:identifier id="bookid">urn:uuid:{ident}</dc:identifier>'
           f"<dc:title>{html.escape(TITLE)}</dc:title><dc:language>en</dc:language>"
           f'<meta property="dcterms:modified">{modified}</meta>'
           f"<dc:description>Revision {html.escape(revision)}, {html.escape(date_text)}</dc:description>"
           "</metadata><manifest>" + "".join(manifest) + f"</manifest><spine>{spine_xml}</spine></package>")
    container = ('<?xml version="1.0"?>\n<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                 '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                 "</rootfiles></container>")
    with zipfile.ZipFile(out_epub, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype", (1980, 1, 1, 0, 0, 0)), "application/epub+zip", zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/style.css", CSS_COMMON + CSS_EPUB, zipfile.ZIP_DEFLATED)
        for name, text in pages.items():
            z.writestr(f"OEBPS/{name}", text, zipfile.ZIP_DEFLATED)


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Build the book as PDF and EPUB into output/.")
    ap.add_argument("revision", help="revision number or label printed on the title page, e.g. 3")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--no-epub", action="store_true")
    ap.add_argument("--date", help="override the generation date (YYYY-MM-DD), for reproducible builds")
    args = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", args.revision):
        sys.exit("build_book: revision may only contain letters, digits, '.', '_' and '-'.")

    day = datetime.date.fromisoformat(args.date) if args.date else datetime.date.today()
    date_text = f"{day.strftime('%B')} {day.day}, {day.year}"

    (ROOT / "build").mkdir(exist_ok=True)
    out_dir = ROOT / "output"
    out_dir.mkdir(exist_ok=True)

    docs, warnings = build_docs(collect_docs())
    for w in warnings:
        print("warning:", w, file=sys.stderr)
    chapters = sum(1 for d in docs if d.kind == "chapter")
    print(f"book: {chapters} chapters, {sum(1 for d in docs if d.kind == 'appendix')} appendices, "
          f"revision {args.revision}, {date_text}")

    stem = f"{FILE_STEM}-r{args.revision}"
    if not args.no_epub:
        make_epub(docs, args.revision, date_text, out_dir / f"{stem}.epub")
        print(f"wrote output/{stem}.epub")
    if not args.no_pdf:
        make_pdf(build_pdf_html(docs, args.revision, date_text), out_dir / f"{stem}.pdf")
        add_bookmarks(out_dir / f"{stem}.pdf", toc_entries(docs))
        print(f"wrote output/{stem}.pdf")


if __name__ == "__main__":
    main()
