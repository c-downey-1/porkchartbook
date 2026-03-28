"""
mmn_client.py — lightweight MyMarketNews report downloader.
"""

from __future__ import annotations

import re
import ssl
import subprocess
import tempfile
from urllib.parse import urljoin
from urllib.request import Request, urlopen


BASE_URL = "https://mymarketnews.ams.usda.gov"
VIEW_REPORT_URL = BASE_URL + "/viewReport/{report_id}"
PUBLISHED_REPORTS_URL = "https://marsapi.ams.usda.gov/services/v3.1/public/listPublishedReports/all"
FILE_LINK_RE = re.compile(r'href="([^"]*?/filerepo/[^"]+\.(txt|pdf|csv|xlsx))"', re.I)
MNREPORT_URL_RE = re.compile(r"https://www\.ams\.usda\.gov/mnreports/(\S+)")
UNVERIFIED_SSL_CONTEXT = ssl._create_unverified_context()
PUBLISHED_REPORTS_CACHE = None


def _fetch_text(url):
    req = Request(url, headers={"User-Agent": "porkchartbook/1.0"})
    with urlopen(req, timeout=120, context=UNVERIFIED_SSL_CONTEXT) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _fetch_bytes(url):
    req = Request(url, headers={"User-Agent": "porkchartbook/1.0"})
    with urlopen(req, timeout=120, context=UNVERIFIED_SSL_CONTEXT) as response:
        return response.read()


def _latest_published_url(report_id):
    global PUBLISHED_REPORTS_CACHE
    if PUBLISHED_REPORTS_CACHE is None:
        PUBLISHED_REPORTS_CACHE = _fetch_text(PUBLISHED_REPORTS_URL)

    report_line = None
    for line in PUBLISHED_REPORTS_CACHE.splitlines():
        if re.match(rf"^\s*{report_id}\s+", line):
            report_line = line
            break
    if not report_line:
        return None

    match = MNREPORT_URL_RE.search(report_line)
    return match.group(0) if match else None


def _pdf_text_from_url(url):
    pdf_bytes = _fetch_bytes(url)
    with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
        handle.write(pdf_bytes)
        handle.flush()
        result = subprocess.run(
            ["pdftotext", "-layout", handle.name, "-"],
            check=True,
            capture_output=True,
            text=True,
        )
    return result.stdout


def report_links(report_id):
    html = _fetch_text(VIEW_REPORT_URL.format(report_id=report_id))
    links = {}
    for href, ext in FILE_LINK_RE.findall(html):
        links.setdefault(ext.lower(), urljoin(BASE_URL, href))
    return links


def fetch_report_text(report_id):
    try:
        links = report_links(report_id)
        txt_url = links.get("txt")
        if txt_url:
            return _fetch_text(txt_url), links
    except Exception:
        links = {}

    latest_url = _latest_published_url(report_id)
    if not latest_url:
        return None, links

    fallback_links = dict(links)
    if latest_url.lower().endswith(".txt"):
        fallback_links.setdefault("txt", latest_url)
        return _fetch_text(latest_url), fallback_links
    if latest_url.lower().endswith(".pdf"):
        fallback_links.setdefault("pdf", latest_url)
        return _pdf_text_from_url(latest_url), fallback_links
    return None, fallback_links
