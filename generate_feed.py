import gzip
import io
import re
from datetime import datetime, timezone
from email.utils import format_datetime

import requests
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

# ==========================================================
# CONFIGURAÇÕES
# ==========================================================

SITE_URL = "https://www.extremeparts.com.br"

ROBOTS_URL = f"{SITE_URL}/robots.txt"

BLOG_URL = f"{SITE_URL}/blog/"

BLOG_TITLE = "Extreme Parts Blog"

BLOG_DESCRIPTION = "Últimos artigos publicados no Blog da Extreme Parts."

FEED_URL = "https://dev-extremeparts.github.io/rss-blog/feed.xml"

MAX_POSTS = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}

session = requests.Session()
session.headers.update(HEADERS)

# ==========================================================
# UTILITÁRIOS
# ==========================================================

def request(url, timeout=30):
    """
    Faz uma requisição com até 3 tentativas.
    """

    last_error = None

    for tentativa in range(3):

        try:

            r = session.get(url, timeout=timeout)

            r.raise_for_status()

            return r

        except Exception as e:

            last_error = e

            print(f"Tentativa {tentativa+1}/3 falhou: {url}")

    raise last_error


def discover_blog_sitemap():

    print("Lendo robots.txt...")

    robots = request(ROBOTS_URL).text

    for line in robots.splitlines():

        if line.lower().startswith("sitemap:"):

            sitemap = line.split(":", 1)[1].strip()

            if "blog" in sitemap:

                print("Sitemap encontrado:")

                print(sitemap)

                return sitemap

    raise Exception("Sitemap do blog não encontrado.")

def read_sitemap():

    sitemap_url = discover_blog_sitemap()

    print("Baixando sitemap...")

    data = request(sitemap_url).content

    if sitemap_url.endswith(".gz"):

        print("Descompactando sitemap...")

        data = gzip.decompress(data)

    root = ET.fromstring(data)

    ns = {
        "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
        "image": "http://www.google.com/schemas/sitemap-image/1.1"
    }

    urls = []

    for url in root.findall("sm:url", ns):

        loc = url.find("sm:loc", ns).text.strip()

        if loc.rstrip("/") == BLOG_URL.rstrip("/"):
            continue

        image = ""

        img = url.find("image:image", ns)

        if img is not None:

            img_loc = img.find("image:loc", ns)

            if img_loc is not None:

                image = img_loc.text.strip()

        urls.append({
            "url": loc,
            "image": image
        })

    print(f"{len(urls)} artigos encontrados.")

    return urls    

# ==========================================================
# EXTRAÇÃO DOS POSTS
# ==========================================================

DATE_REGEX = re.compile(r"Publicado em\s+(\d{2}/\d{2}/\d{4})", re.IGNORECASE)


def get_meta(soup, prop=None, name=None):
    """
    Retorna o conteúdo de uma meta tag.
    """

    if prop:
        tag = soup.find("meta", property=prop)
        if tag and tag.get("content"):
            return tag["content"].strip()

    if name:
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return tag["content"].strip()

    return ""


def parse_date(text):
    """
    Procura por:
    Publicado em DD/MM/AAAA
    """

    m = DATE_REGEX.search(text)

    if not m:
        return datetime.now(timezone.utc)

    try:

        dt = datetime.strptime(m.group(1), "%d/%m/%Y")

        return dt.replace(tzinfo=timezone.utc)

    except Exception:

        return datetime.now(timezone.utc)


def parse_post(post):

    url = post["url"]

    print(f"Lendo artigo: {url}")

    try:

        response = request(url)

    except Exception as e:

        print("Erro:", e)

        return None

    soup = BeautifulSoup(response.text, "lxml")

    # -------------------------
    # TÍTULO
    # -------------------------

    title = get_meta(soup, prop="og:title")

    if not title:

        h1 = soup.find("h1")

        if h1:
            title = h1.get_text(" ", strip=True)

    if not title and soup.title:

        title = soup.title.get_text(" ", strip=True)

    # -------------------------
    # DESCRIÇÃO
    # -------------------------

    description = get_meta(soup, prop="og:description")

    if not description:

        description = get_meta(soup, name="description")

    # -------------------------
    # IMAGEM
    # -------------------------

    image = post["image"]

    if not image:

        image = get_meta(soup, prop="og:image")

    # -------------------------
    # DATA
    # -------------------------

    page_text = soup.get_text(" ", strip=True)

    published = parse_date(page_text)

    return {
        "title": title,
        "description": description,
        "link": url,
        "image": image,
        "published": published,
    }


def load_posts():

    sitemap_posts = read_sitemap()

    posts = []

    for item in sitemap_posts:

        post = parse_post(item)

        if post:

            posts.append(post)

    posts.sort(
        key=lambda x: x["published"],
        reverse=True
    )

    posts = posts[:MAX_POSTS]

    print()

    print(f"{len(posts)} artigos processados.")

    return posts    

# ==========================================================
# GERAÇÃO DO RSS
# ==========================================================

def generate_feed(posts):

    print("Gerando RSS...")

    fg = FeedGenerator()

    fg.id(BLOG_URL)
    fg.title(BLOG_TITLE)
    fg.link(href=BLOG_URL, rel="alternate")
    fg.link(href=FEED_URL, rel="self")
    fg.description(BLOG_DESCRIPTION)
    fg.language("pt-BR")
    fg.generator("GitHub Actions + FeedGen")

    if posts:
        fg.lastBuildDate(posts[0]["published"])

    for post in posts:

        fe = fg.add_entry()

        fe.id(post["link"])

        fe.title(post["title"])

        fe.link(href=post["link"])

        fe.description(post["description"])

        fe.pubDate(post["published"])

        if post["image"]:

            fe.enclosure(
                post["image"],
                "0",
                "image/jpeg"
            )

    fg.rss_file("feed.xml", pretty=True)

    print("feed.xml criado com sucesso.")    

# ==========================================================
# MAIN
# ==========================================================

def main():

    print("=" * 60)
    print("RSS Generator - Extreme Parts")
    print("=" * 60)

    posts = load_posts()

    generate_feed(posts)

    print()
    print("Concluído!")


if __name__ == "__main__":
    main()    