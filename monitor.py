"""Monitor przetargów foto/wideo - 3 platformy"""
import os
import asyncio
import json
import re
from datetime import datetime
from playwright.async_api import async_playwright
import httpx

# Frazy do wyszukiwania
SEARCH_PHRASES = [
    "fotografia", "fotograf", "zdjęcia", "zdjęcie",
    "film", "film promocyjny", "film korporacyjny", "film reklamowy",
    "film instruktażowy", "film szkoleniowy", "reportaż filmowy",
    "produkcja filmowa", "produkcja wideo", "realizacja filmów",
    "realizacja wideo", "filmowanie", "spot reklamowy",
    "spot promocyjny", "operator kamery", "operator drona",
    "sesja zdjęciowa", "sesja fotograficzna", "wideo",
    "dokumentacja fotograficzna", "dokumentacja filmowa",
    "materiały promocyjne", "materiały wideo",
    "fotografia lotnicza", "animacja", "postprodukcja",
    "kamerzysta", "fotograf eventowy",
]

# Słowa kluczowe — co MUSI być w tytule oferty żeby pasowała
KEYWORDS = [
    "fotograf", "fotograficzn", "zdjęć", "zdjęci", "zdjęcia",
    "film promocyjn", "film korporacyjn", "film reklamow",
    "film instruktażow", "film szkolen", "filmu", "filmów",
    "filmow", "filmowan", "produkcja film", "realizacja film",
    "produkcja wideo", "realizacja wideo", "reportaż",
    "spot reklamow", "spot promocyjn", "operator kamery",
    "operator drona", "sesja zdjęciow", "sesja fotograficzn",
    "wideo", "kamerzysta", "audiowizualn", "audycji telewizyjn",
    "animacja", "postprodukc",
]

# Słowa wykluczające — jeśli w tytule jest któreś, oferta jest IGNOROWANA
# (np. dostawa sprzętu, naprawa kamer itd. — to nie nasze usługi)
EXCLUDE_KEYWORDS = [
    "dostawa sprzęt", "zakup sprzęt", "naprawa", "konserwacja",
    "remont", "modernizacja sprzęt", "wynajem sprzęt",
    "części zamienn", "akcesori", "filtr",
]

# Cała Polska (bez priorytetów regionów)
LOCAL_KEYWORDS = [
    "wrocław", "wroclaw", "dolnośląsk", "dolnoslaski", "dolny śląsk",
    "legnica", "wałbrzych", "walbrzych", "jelenia", "lubin",
    "świdnica", "swidnica", "głogów", "glogow", "polkowice",
    "oleśnica", "olesnica", "oława", "olawa", "trzebnica",
    "bolesławiec", "boleslawiec", "dzierżoniów", "dzierzoniow",
    "zgorzelec", "ząbkowice",
]


def normalize(text):
    if not text:
        return ""
    table = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "aceelnoszzACEELNOSZZ")
    return text.lower().translate(table)


def is_local(text):
    n = normalize(text)
    return any(normalize(k) in n for k in LOCAL_KEYWORDS)


def is_excluded(text):
    n = normalize(text)
    return any(normalize(k) in n for k in EXCLUDE_KEYWORDS)


def matches_keyword(text):
    n = normalize(text)
    if is_excluded(text):
        return None
    for k in KEYWORDS:
        if normalize(k) in n:
            return k
    return None


# ─── 1. PLATFORMAZAKUPOWA.PL ────────────────────────────────────────────────────

async def search_platformazakupowa(page):
    results = []
    print("\n→ platformazakupowa.pl")
    seen_urls = set()

    for phrase in SEARCH_PHRASES[:15]:  # ograniczamy bo każda fraza = jedno żądanie
        try:
            url = f"https://platformazakupowa.pl/all?q={phrase}"
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            # Akceptuj cookies
            try:
                btn = await page.query_selector('button:has-text("Akceptuj"), [id*="cookie"] button')
                if btn:
                    await btn.click()
                    await page.wait_for_timeout(400)
            except Exception:
                pass

            cards = await page.query_selector_all('a[href*="/transakcja/"]')

            for card in cards:
                try:
                    title = (await card.inner_text()).strip()
                    if not title or len(title) < 15:
                        continue
                    href = await card.get_attribute("href")
                    if not href:
                        continue
                    full_url = href if href.startswith("http") else f"https://platformazakupowa.pl{href}"
                    if full_url in seen_urls:
                        continue

                    kw = matches_keyword(title)
                    if not kw:
                        continue

                    seen_urls.add(full_url)
                    results.append({
                        "title": title[:250], "url": full_url,
                        "source": "platformazakupowa.pl",
                        "keyword": kw, "local": is_local(title),
                    })
                except Exception:
                    continue
        except Exception as e:
            print(f"  ✗ '{phrase}': {str(e)[:60]}")

    print(f"  ✓ {len(results)} pasujących")
    return results


# ─── 2. PLATFORMAOFERTOWA.PL ────────────────────────────────────────────────────

async def search_platformaofertowa(page):
    results = []
    print("\n→ platformaofertowa.pl")
    seen_urls = set()

    # Ta strona ma SPA z polem wyszukiwania
    base = "https://platformaofertowa.pl/pl/tenders/tenders-list-ended"

    for phrase in ["film", "fotografia", "wideo", "zdjęcia", "filmowanie", "reportaż", "operator", "spot"]:
        try:
            url = f"{base}?phrase={phrase}"
            await page.goto(url, wait_until="networkidle", timeout=45000)
            await page.wait_for_timeout(3500)

            # Akceptuj cookies jeśli wyskoczy
            try:
                btn = await page.query_selector('button:has-text("Akceptuj"), button:has-text("Zgoda")')
                if btn:
                    await btn.click()
                    await page.wait_for_timeout(500)
            except Exception:
                pass

            # Spróbuj wpisać frazę w pole wyszukiwania jeśli URL nie zadziałał
            try:
                search_input = await page.query_selector('input[type="search"], input[placeholder*="szukaj"], input[placeholder*="zukaj"]')
                if search_input:
                    cur = await search_input.input_value()
                    if not cur or phrase not in cur.lower():
                        await search_input.fill(phrase)
                        await search_input.press("Enter")
                        await page.wait_for_timeout(3500)
            except Exception:
                pass

            # Szukamy kart z ofertami
            # Każda oferta ma tytuł + zamawiający + termin
            html = await page.content()

            # Wyciągamy bloki z tytułami (są to nagłówki h3/h2/strong w cards)
            cards = await page.query_selector_all('a[href*="/tender"], a[href*="/oferta"], .tender-card a, [class*="result"] a, [class*="offer"] a')

            for card in cards:
                try:
                    title = (await card.inner_text()).strip()
                    if not title or len(title) < 15:
                        continue
                    href = await card.get_attribute("href")
                    if not href:
                        continue
                    full_url = href if href.startswith("http") else f"https://platformaofertowa.pl{href}"
                    if full_url in seen_urls or "list-ended" in full_url:
                        continue

                    # Pobierz kontekst
                    parent = await card.evaluate("el => el.closest('article, .card, [class*=tender], [class*=offer], li, tr')?.innerText || ''")
                    full_text = title + " " + (parent or "")[:500]

                    kw = matches_keyword(full_text)
                    if not kw:
                        continue

                    seen_urls.add(full_url)
                    results.append({
                        "title": title[:250], "url": full_url,
                        "source": "platformaofertowa.pl",
                        "keyword": kw, "local": is_local(full_text),
                    })
                except Exception:
                    continue
        except Exception as e:
            print(f"  ✗ '{phrase}': {str(e)[:60]}")

    print(f"  ✓ {len(results)} pasujących")
    return results


# ─── 3. BAZA KONKURENCYJNOŚCI ───────────────────────────────────────────────────

async def search_baza_konkurencyjnosci(page):
    results = []
    print("\n→ Baza Konkurencyjności")
    base_url = "https://bazakonkurencyjnosci.funduszeeuropejskie.gov.pl"
    seen_urls = set()

    for phrase in ["fotografia", "wideo", "film promocyjny", "filmowanie", "reportaż", "operator kamery"]:
        try:
            await page.goto(
                f"{base_url}/ogloszenia?phrase={phrase}&status=ACTIVE",
                wait_until="domcontentloaded", timeout=30000
            )
            await page.wait_for_timeout(3000)

            links = await page.query_selector_all('a[href*="/ogloszenia/"]')
            for link in links:
                try:
                    text = (await link.inner_text()).strip()
                    if not text or len(text) < 15:
                        continue
                    href = await link.get_attribute("href")
                    if not href or "phrase=" in href or href.endswith("/ogloszenia"):
                        continue
                    url = href if href.startswith("http") else f"{base_url}{href}"
                    if url in seen_urls:
                        continue

                    parent = await link.evaluate(
                        "el => el.closest('article, .tile, .ogloszenie, li')?.innerText || ''"
                    )
                    full_text = text + " " + (parent or "")

                    kw = matches_keyword(full_text)
                    if not kw:
                        continue

                    seen_urls.add(url)
                    results.append({
                        "title": text[:250], "url": url,
                        "source": "Baza Konkurencyjności",
                        "keyword": kw, "local": is_local(full_text),
                    })
                except Exception:
                    continue
        except Exception as e:
            print(f"  ✗ '{phrase}': {str(e)[:60]}")

    print(f"  ✓ {len(results)} pasujących")
    return results


# ─── TELEGRAM ───────────────────────────────────────────────────────────────────

async def send_telegram(text):
    tg_token = os.getenv("TELEGRAM_TOKEN", "")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if not tg_token or not tg_chat:
        print("⚠ Brak Telegrama")
        return False

    # Telegram limit: 4096 znaków
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]

    url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
    async with httpx.AsyncClient() as client:
        for chunk in chunks:
            try:
                r = await client.post(url, json={
                    "chat_id": tg_chat, "text": chunk,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                }, timeout=20)
                if r.status_code != 200:
                    # Jeśli Markdown failuje, próbujemy bez parse_mode
                    print(f"  retry without markdown: {r.status_code}")
                    await client.post(url, json={
                        "chat_id": tg_chat, "text": chunk,
                        "disable_web_page_preview": True,
                    }, timeout=20)
            except Exception as e:
                print(f"  ✗ Telegram: {e}")
                return False
    print("✓ Telegram: wysłano")
    return True


def format_message(local, national, date):
    total = len(local) + len(national)
    if total == 0:
        return f"📸 *Monitor Przetargów Foto/Wideo*\n📅 {date}\n\n😴 Brak nowych ogłoszeń dziś."

    lines = [
        f"📸 *Monitor Przetargów Foto/Wideo*",
        f"📅 {date} — *{total}* ogłoszeń\n",
    ]

    def esc(s):
        # Escape Markdown special chars in text (but not in URL)
        return s.replace("[", "(").replace("]", ")").replace("_", " ").replace("*", "·").replace("`", "'")[:100]

    if local:
        lines.append(f"📍 *Dolny Śląsk / Wrocław* ({len(local)})")
        for i, r in enumerate(local[:15], 1):
            src = r.get('source', '').split('.')[0][:6]
            lines.append(f"{i}. [{esc(r['title'])}]({r['url']}) `{src}`")
        if len(local) > 15:
            lines.append(f"_...i {len(local) - 15} więcej_")
        lines.append("")

    if national:
        lines.append(f"🇵🇱 *Cała Polska* ({len(national)})")
        for i, r in enumerate(national[:20], 1):
            src = r.get('source', '').split('.')[0][:6]
            lines.append(f"{i}. [{esc(r['title'])}]({r['url']}) `{src}`")
        if len(national) > 20:
            lines.append(f"_...i {len(national) - 20} więcej_")

    return "\n".join(lines)


# ─── MAIN ───────────────────────────────────────────────────────────────────────

async def main():
    print(f"=== Monitor Przetargów — {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
    all_results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="pl-PL",
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        for fn in [search_platformazakupowa, search_platformaofertowa, search_baza_konkurencyjnosci]:
            try:
                r = await fn(page)
                all_results.extend(r)
            except Exception as e:
                print(f"  ✗ fatal: {e}")

        await browser.close()

    # Dedup
    seen = set()
    unique = []
    for r in all_results:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)

    local = [r for r in unique if r["local"]]
    national = [r for r in unique if not r["local"]]

    print(f"\n=== Wyniki ===")
    print(f"Łącznie unikalnych: {len(unique)}")
    print(f"Dolny Śląsk: {len(local)}")
    print(f"Cała Polska: {len(national)}")

    msg = format_message(local, national, datetime.now().strftime("%d.%m.%Y"))
    await send_telegram(msg)

    with open("results.json", "w", encoding="utf-8") as f:
        json.dump({
            "date": datetime.now().isoformat(),
            "local": local, "national": national,
        }, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
