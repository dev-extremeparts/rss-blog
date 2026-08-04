import re
import requests
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from datetime import datetime, timezone
from email.utils import format_datetime

SITEMAP_URL = "https://www.extremeparts.com.br/sitemap_blog.xml"

BLOG_TITLE = "Extreme Parts Blog"
BLOG_LINK = "https://www.extremeparts.com.br/blog/"
BLOG_DESCRIPTION = "Últimos artigos publicados no blog da Extreme Parts."

MAX_ITEMS = 30

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RSSFeedBot/1.0)"
}


def get_meta(soup, property_name=None, name=None):
    if property_name:
        tag = soup.find("meta", property=property_name)
        if tag:
            return tag.get("content", "").strip()

    if name:
        tag = soup.find("meta", attrs={"name": name})
        if tag:
            return tag.get("content", "").strip()

    return ""


print("Baixando sitemap...")

resp = requests.get(SITEMAP_URL, headers=HEADERS, timeout=30)
resp.raise_for_status()

root = ET.fromstring(resp.content)

ns = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "image": "http://www.google.com/schemas/sitemap-image/1.1"
}

posts = []

for url in root.findall("sm:url", ns):

    loc = url.find("sm:loc", ns).text.strip()

    # ignora a home do blog
    if loc.rstrip("/") == BLOG_LINK.rstrip("/"):
        continue

    image = ""

    image_tag = url.find("image:image", ns)
    if image_tag is not None:
        image_loc = image_tag.find("image:loc", ns)
        if image_loc is not None:
            image = image_loc.text.strip()

    print("Lendo:", loc)

    try:

        page = requests.get(loc, headers=HEADERS, timeout=30)
        page.raise_for_status()

        soup = BeautifulSoup(page.text, "lxml")

        title = get_meta(soup, property_name="og:title")

        if not title:
            h1 = soup.find("h1")
            if h1:
                title = h1.get_text(strip=True)

        if not title and soup.title:
            title = soup.title.get_text(strip=True)

        description = (
            get_meta(soup, property_name="og:description")
            or get_meta(soup, name="description")
        )

        if not image:
            image = get_meta(soup, property_name="og:image")

        # Procura a data no texto "Publicado em DD/MM/AAAA"
        text = soup.get_text(" ", strip=True)

        m = re.search(r"Publicado em (\d{2}/\d{2}/\d{4})", text)

        if m:
            dt = datetime.strptime(m.group(1), "%d/%m/%Y")
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = datetime.now(timezone.utc)

        posts.append({
            "title": title,
            "description": description,
            "link": loc,
            "image": image,
            "date": dt
        })

    except Exception as e:
        print(f"Erro em {loc}: {e}")

posts.sort(key=lambda x: x["date"], reverse=True)

posts = posts[:MAX_ITEMS]

rss = f'''<?xml version="1.0" encoding="UTF-8"?>

<rss version="2.0"
xmlns:media="http://search.yahoo.com/mrss/"
xmlns:atom="http://www.w3.org/2005/Atom">

<channel>

<title>{BLOG_TITLE}</title>

<link>{BLOG_LINK}</link>

<description>{BLOG_DESCRIPTION}</description>

<language>pt-BR</language>

<atom:link
href="feed.xml"
rel="self"
type="application/rss+xml"/>

'''

for post in posts:

    rss += f"""
<item>

<title><![CDATA[{post['title']}]]></title>

<link>{post['link']}</link>

<guid isPermaLink="true">{post['link']}</guid>

<pubDate>{format_datetime(post['date'])}</pubDate>

<description><![CDATA[{post['description']}]]></description>
"""

    if post["image"]:
        rss += f"""
<media:content
url="{post['image']}"
medium="image"/>
"""

    rss += """

</item>

"""

rss += """

</channel>

</rss>
"""

with open("feed.xml", "w", encoding="utf-8") as f:
    f.write(rss)

print()
print(f"RSS gerado com {len(posts)} artigos.")
print("Arquivo salvo como feed.xml")