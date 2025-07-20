# app.py

from flask import Flask, request, jsonify
from urllib.parse import urljoin, urlparse
import os, re, time, random, requests, bs4

app = Flask(__name__)
API_TOKEN = os.getenv("API_TOKEN")

# Regex pour extraire les e-mails
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# User‑Agent pour les requêtes
HEADERS = {"User-Agent": "Mozilla/5.0 EmailBot/1.0"}

# Mots‑clés priorisés dans les chemins
KEYWORDS = ["contact", "mention", "legal", "email", "equipe", "team", "about", "support"]

# Extensions de fichiers à ignorer (assets/images/etc.)
IGNORE_EXT = re.compile(r".*\.(jpg|jpeg|png|gif|svg|css|js|pdf|zip|mp4|avi)$", re.IGNORECASE)


def normalize(link, base_url):
    """Transforme un lien relatif en URL absolue et enlève le fragment."""
    joined = urljoin(base_url, link)
    p = urlparse(joined)
    return f"{p.scheme}://{p.netloc}{p.path}" + (f"?{p.query}" if p.query else "")


def is_internal(url, base_netloc):
    """Vérifie si une URL est interne au domaine de base."""
    p = urlparse(url)
    return (not p.netloc) or (p.netloc == base_netloc)


@app.route("/scrape", methods=["POST"])
def scrape():
    # Auth (optionnel)
    if API_TOKEN and request.headers.get("X-API-KEY") != API_TOKEN:
        return jsonify({"error": "unauthorized"}), 401

    data      = request.get_json(force=True)
    raw_url   = data.get("url", "").strip()
    max_pages = data.get("max_pages", 100)
    if not raw_url:
        return jsonify({"error": "url missing"}), 400

    # Normalisation de l'URL de départ
    if not urlparse(raw_url).scheme:
        raw_url = "https://" + raw_url
    base_netloc = urlparse(raw_url).netloc

    # Structures de crawl
    to_visit     = [raw_url]
    visited      = set()
    found_emails = set()
    pages_crawled = 0

    while to_visit and pages_crawled < max_pages:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)
        pages_crawled += 1

        try:
            resp = requests.get(url, headers=HEADERS, timeout=8, allow_redirects=True)
            resp.raise_for_status()
        except Exception:
            continue

        soup = bs4.BeautifulSoup(resp.text, "lxml")
        text = soup.get_text(separator=" ")

        # Extraction des e‑mails
        for m in EMAIL_RE.findall(text):
            found_emails.add(m)
        for a in soup.select("a[href^=mailto]"):
            mail = a["href"].split("mailto:")[-1]
            if mail:
                found_emails.add(mail)

        # Si on a trouvé au moins un e‑mail, on arrête tout de suite
        if found_emails:
            break

        # Découverte de nouveaux liens internes, priorisés
        for a in soup.select("a[href]"):
            raw_link = a["href"]
            norm     = normalize(raw_link, url)
            if is_internal(norm, base_netloc) and norm not in visited and not IGNORE_EXT.match(norm):
                path = urlparse(norm).path.lower()
                if any(kw in path for kw in KEYWORDS):
                    to_visit.insert(0, norm)   # priorité haute
                else:
                    to_visit.append(norm)      # priorité basse

        # Pause réduite pour aller plus vite
        time.sleep(random.uniform(0.2, 0.5))

    return jsonify({
        "start_url": raw_url,
        "pages_crawled": pages_crawled,
        "emails": sorted(found_emails)
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
