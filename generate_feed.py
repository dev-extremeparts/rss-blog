import gzip
import io
import re
import time
from datetime import datetime, timezone
from email.utils import format_datetime

import requests
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

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
        "Chrome/133.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

session = requests.Session()
session.headers.update(HEADERS)

# ==========================================================
# UTILITÁRIOS
# ==========================================================

def request(url, timeout=30):
    """
    Faz uma requisição HTTP com suporte a impersonate (curl_cffi) para ignorar
    bloqueios 403 Forbidden do Cloudflare/Tiendanube, com fallback e tentativas com backoff.
    """
    last_error = None

    for tentativa in range(3):
        try:
            if HAS_CURL_CFFI:
                try:
                    r = curl_requests.get(url, impersonate="chrome", timeout=timeout)
                    r.raise_for_status()
                    return r
                except Exception as e_curl:
                    r = session.get(url, timeout=timeout)
                    r.raise_for_status()
                    return r
            else:
                r = session.get(url, timeout=timeout)
                r.raise_for_status()
                return r
        except Exception as e:
            last_error = e
            print(f"Tentativa {tentativa+1}/3 falhou: {url}")
            if tentativa < 2:
                time.sleep(2 * (tentativa + 1))

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

    print(f"{len(urls)} artigos encontrados no sitemap.")
    return urls    

# ==========================================================
# EXTRAÇÃO DOS POSTS
# ==========================================================

DATE_REGEX = re.compile(r"Publicado em\s+(\d{2}/\d{2}/\d{4})", re.IGNORECASE)


def extract_date_from_image_url(image_url):
    """
    Extrai o timestamp de uma imagem com UUIDv7 na URL (ex: CDN Tiendanube).
    """
    if not image_url:
        return None
    m = re.search(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', image_url, re.IGNORECASE)
    if m:
        try:
            hex_ms = m.group(1).replace('-', '')[:12]
            ts_ms = int(hex_ms, 16)
            return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
        except Exception:
            pass
    return None


def title_from_url(url):
    """
    Gera um título legível a partir da slug da URL caso a página bloqueie raspagem.
    """
    slug = url.rstrip('/').split('/')[-1]
    slug = re.sub(r'-[0-9a-f]{8,12}$', '', slug, flags=re.IGNORECASE)
    words = slug.split('-')
    return ' '.join(w.capitalize() for w in words)


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


def parse_date(text, soup=None, image_url=None):
    """
    Procura por data de publicação via meta tags, tag <time>, regex ou UUIDv7 da imagem.
    """
    if soup:
        pub_time = get_meta(soup, prop="article:published_time")
        if pub_time:
            try:
                return datetime.fromisoformat(pub_time.replace("Z", "+00:00"))
            except Exception:
                pass

        time_tag = soup.find("time")
        if time_tag and time_tag.get("datetime"):
            try:
                return datetime.fromisoformat(time_tag["datetime"].replace("Z", "+00:00"))
            except Exception:
                pass

    m = DATE_REGEX.search(text)
    if m:
        try:
            dt = datetime.strptime(m.group(1), "%d/%m/%Y")
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass

    # Fallback para timestamp extraído do UUIDv7 da imagem de capa
    img_date = extract_date_from_image_url(image_url)
    if img_date:
        return img_date

    return datetime.now(timezone.utc)


def parse_post(post):
    url = post["url"]
    image = post["image"]

    print(f"Lendo artigo: {url}")

    soup = None
    try:
        response = request(url)
        soup = BeautifulSoup(response.text, "lxml")
    except Exception as e:
        print(f"Aviso ao acessar {url}: {e}")
        print("  -> Utilizando metadados de fallback do sitemap...")

    if soup:
        title = get_meta(soup, prop="og:title")
        if not title:
            h1 = soup.find("h1")
            if h1:
                title = h1.get_text(" ", strip=True)
        if not title and soup.title:
            title = soup.title.get_text(" ", strip=True)

        description = get_meta(soup, prop="og:description")
        if not description:
            description = get_meta(soup, name="description")

        if not image:
            image = get_meta(soup, prop="og:image")

        page_text = soup.get_text(" ", strip=True)
        published = parse_date(page_text, soup, image)
    else:
        # Fallback de emergência caso o site retorne 403 Forbidden ou falhe
        title = title_from_url(url)
        description = title
        published = extract_date_from_image_url(image) or datetime.now(timezone.utc)

    title_clean = title or title_from_url(url)
    return {
        "title": title_clean,
        "description": description or title_clean,
        "link": url,
        "image": image or "",
        "published": published,
    }


def load_posts():
    sitemap_posts = read_sitemap()
    posts = []

    for item in sitemap_posts:
        post = parse_post(item)
        if post:
            posts.append(post)
        time.sleep(0.5)

    posts.sort(
        key=lambda x: x["published"],
        reverse=True
    )

    posts = posts[:MAX_POSTS]

    print()
    print(f"{len(posts)} artigos processados com sucesso.")
    return posts    

# ==========================================================
# GERAÇÃO DO RSS
# ==========================================================

def generate_feed(posts):
    if not posts:
        raise RuntimeError("Nenhum post foi processado. Abortando para não gerar um feed vazio.")

    print("Gerando RSS...")

    fg = FeedGenerator()

    fg.id(BLOG_URL)
    fg.title(BLOG_TITLE)
    fg.link(href=BLOG_URL, rel="alternate")
    fg.link(href=FEED_URL, rel="self")
    fg.description(BLOG_DESCRIPTION)
    fg.language("pt-BR")
    fg.generator("GitHub Actions + FeedGen")

    fg.lastBuildDate(posts[0]["published"])

    for post in posts:
        fe = fg.add_entry(order="append")
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