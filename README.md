# RSS Blog - Extreme Parts

Gerador automático de feed RSS 2.0 para o blog da [Extreme Parts](https://www.extremeparts.com.br/blog/).

## 📌 Feed Publicado

O feed RSS atualizado está publicamente acessível no GitHub Pages:
👉 **[https://dev-extremeparts.github.io/rss-blog/feed.xml](https://dev-extremeparts.github.io/rss-blog/feed.xml)**

---

## 🛠️ Como Funciona

1. **Descoberta Dinâmica**: Lê o `robots.txt` do site para localizar o arquivo `sitemap_blog.xml.gz`.
2. **Download & Descompactação**: Baixa o sitemap do blog e descompacta os artigos em memória.
3. **Extração de Metadados**:
   - Utiliza `curl_cffi` para impersonar a assinatura TLS de navegadores e ignorar bloqueios `403 Forbidden` de WAF / Cloudflare / Tiendanube.
   - Extrai título (`og:title`), descrição (`og:description`), imagem de capa (`og:image`) e data de publicação.
   - Possui lógica de *fallback* para extrair a data a partir do UUIDv7 da imagem de capa caso a data no HTML falhe.
4. **Geração do Feed**: Cria o arquivo `feed.xml` no formato RSS 2.0 padrão utilizando `feedgen`.
5. **Automação Diária**: Uma rotina no **GitHub Actions** executa o script diariamente às 06:00 (BRT) e atualiza o repositório.

---

## 🚀 Executando Localmente

### Pré-requisitos
- Python 3.10+ instalado

### Instalação

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Executar o gerador
python generate_feed.py
```

---

## 📄 Licença

Copyright (c) 2026 **EXTREME PARTS**. Todos os direitos reservados.