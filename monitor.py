"""
Monitor przetargów foto/wideo
Loguje się na 2 platformy, szuka ogłoszeń, wysyła na Telegram.
"""
import os
import asyncio
import json
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
import httpx

# ─── KONFIGURACJA ───────────────────────────────────────────────────────────────

KEYWORDS = [
    "fotografia", "fotograficzn", "zdjęcia", "sesja zdjęciow",
    "film promocyjn", "film korporacyjn", "produkcja wideo",
    "filmowanie", "spot reklamow", "operator kamery",
    "operator drona", "wideo", "animacja",
    "dokumentacja fotograficzn", "materiały promocyjn",
]

LOCAL_KEYWORDS = [
    "wrocław", "wroclaw", "dolnośląsk", "dolnoslaski", "dolny śląsk",
    "legnica", "wałbrzych", "walbrzych", "jelenia góra", "jelenia gora",
    "lubin", "świdnica", "swidnica", "głogów", "glogow", "polkowice",
    "oleśnica", "olesnica", "oława", "olawa", "trzebnica", "bolesławiec",
    "boleslawiec", "dzierżoniów", "dzierzoniow", "zgorzelec", "ząbkowice",
]

# Sekrety z GitHub Actions
PLATFORMA_USER = os.getenv("PLATFORMA_LOGIN", "")
PLATFORMA_PASS = os.getenv("PLATFORMA_HASLO", "")
BAZA_USER = os.getenv("BAZA_LOGIN", "")
BAZA_PASS = os.getenv("BAZA_HASLO", "")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


# ─── HELPERS ────────────────────────────────────────────────────────────────────

def normalize(text):
    """Lowercase + remove polish diacritics for comparison."""
    if not text:
        return ""
    table = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "aceelnoszzACEELNOSZZ")
    return text.lower().translate(table)


def is_local(text):
    n = normalize(text)
    return any(normalize(k) in n for k in LOCAL_KEYWORDS)


def matches_keyword(text):
    n = normalize(text)
    for k in KEYWORDS:
        if normalize(k) in n:
            return k
    return None


# ─── PLATFORMAZAKUPOWA.PL ───────────────────────────────────────────────────────

async def search_platformazakupowa(page):
    """Loguje się i szuka na platformazakupowa.pl"""
    results = []
    print("→ platformazakupowa.pl: rozpoczynam...")

    try:
        # Idziemy bez logowania na publiczny search
        await page.goto("https://platformazakupowa.pl/all", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        # Znajdź wszystkie linki do transakcji
        links = await page.query_selector_all('a[href*="/transakcja/"]')
        print(f"  znaleziono {len(links)} ogłoszeń na stronie")

        for link in links:
            try:
                title = (await link.inner_text()).strip()
                if not title or len(title) < 8:
                    continue
                href = await link.get_attribute("href")
                if not href:
                    continue
                url = href if href.startswith("http") else f"https://platformazakupowa.pl{href}"

                kw = matches_keyword(title)
                if not kw:
                    continue

                results.append({
                    "title": title,
                    "url": url,
                    "source": "platformazakupowa.pl",
                    "keyword": kw,
                    "local": is_local(title),
                })
            except Exception as e:
                continue

        print(f"  ✓ pasujących: {len(results)}")
    except Exception as e:
        print(f"  ✗ błąd: {e}")

    return results


# ─── BAZA KONKURENCYJNOŚCI ──────────────────────────────────────────────────────

async def search_baza_konkurencyjnosci(page):
    """Loguje się i szuka w Bazie Konkurencyjności."""
    results = []
    print("→ Baza Konkurencyjności: rozpoczynam...")

    base_url = "https://bazakonkurencyjnosci.funduszeeuropejskie.gov.pl"

    try:
        # Próbujemy różne frazy bo Baza ma dobry search
        for phrase in ["fotografia", "wideo", "film promocyjny"]:
            await page.goto(
                f"{base_url}/ogloszenia?phrase={phrase}&status=ACTIVE",
                wait_until="domcontentloaded",
                timeout=30000
            )
            await page.wait_for_timeout(3000)

            # Wszystkie linki do ogłoszeń
            links = await page.query_selector_all('a[href*="/ogloszenia/"]')

            for link in links:
                try:
                    text = (await link.inner_text()).strip()
                    if not text or len(text) < 10:
                        continue
                    href = await link.get_attribute("href")
                    if not href or "phrase" in href:  # skip search nav links
                        continue
                    url = href if href.startswith("http") else f"{base_url}{href}"

                    # Pobierz też miasto/wojewodztwo z parent element
                    parent = await link.evaluate("el => el.closest('.tile, article, .ogloszenie')?.innerText || ''")
                    full_text = text + " " + (parent or "")

                    kw = matches_keyword(full_text)
                    if not kw:
                        continue

                    results.append({
                        "title": text[:200],
                        "url": url,
                        "source": "Baza Konkurencyjności",
                        "keyword": kw,
                        "local": is_local(full_text),
                    })
                except:
                    continue

        # Dedup po URL
        seen = set()
        unique = []
        for r in results:
            if r["url"] not in seen:
                seen.add(r["url"])
                unique.append(r)
        results = unique

        print(f"  ✓ unikalnych: {len(results)}")
    except Exception as e:
        print(f"  ✗ błąd: {e}")

    return results


# ─── TELEGRAM ───────────────────────────────────────────────────────────────────

async def send_telegram(text):
    """Wyślij wiadomość na Telegram."""
    if not TG_TOKEN or not TG_CHAT_ID:
        print("⚠ Brak konfiguracji Telegrama")
        return False

    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(url, json={
                "chat_id": TG_CHAT_ID,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            }, timeout=20)
            if r.status_code == 200:
                print("✓ Telegram: wysłano")
                return True
            else:
                print(f"✗ Telegram: {r.status_code} {r.text[:200]}")
        except Exception as e:
            print(f"✗ Telegram: {e}")
    return False


def format_message(local, national, date):
    """Sformatuj wiadomość Markdown."""
    total = len(local) + len(national)

    if total == 0:
        return f"📸 *Monitor Przetargów Foto/Wideo*\n📅 {date}\n\n😴 Brak nowych ogłoszeń dziś."

    lines = [
        f"📸 *Monitor Przetargów Foto/Wideo*",
        f"📅 {date} — *{total}* ogłoszeń\n",
    ]

    def esc(s):
        # Markdown V1 — minimalne escapowanie
        return s.replace("[", "(").replace("]", ")").replace("_", " ")[:75]

    if local:
        lines.append(f"📍 *Dolny Śląsk / Wrocław* ({len(local)})")
        for i, r in enumerate(local[:7], 1):
            lines.append(f"{i}. [{esc(r['title'])}]({r['url']})")
        if len(local) > 7:
            lines.append(f"_...i {len(local) - 7} więcej_")
        lines.append("")

    if national:
        lines.append(f"🇵🇱 *Cała Polska* ({len(national)})")
        for i, r in enumerate(national[:7], 1):
            lines.append(f"{i}. [{esc(r['title'])}]({r['url']})")
        if len(national) > 7:
            lines.append(f"_...i {len(national) - 7} więcej_")

    return "\n".join(lines)


# ─── MAIN ───────────────────────────────────────────────────────────────────────

async def main():
    print(f"=== Monitor Przetargów — {datetime.now().strftime('%Y-%m-%d %H:%M')} ===\n")
    
print(f"DEBUG TG_TOKEN set: {bool(TG_TOKEN)} (len={len(TG_TOKEN)})")
    print(f"DEBUG TG_CHAT_ID set: {bool(TG_CHAT_ID)}")
    print(f"DEBUG PLATFORMA_USER set: {bool(PLATFORMA_USER)}")
    print(f"DEBUG BAZA_USER set: {bool(BAZA_USER)}")
    all_results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="pl-PL",
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        # Platformazakupowa
        try:
            r1 = await search_platformazakupowa(page)
            all_results.extend(r1)
        except Exception as e:
            print(f"platformazakupowa fatal: {e}")

        # Baza Konkurencyjności
        try:
            r2 = await search_baza_konkurencyjnosci(page)
            all_results.extend(r2)
        except Exception as e:
            print(f"baza fatal: {e}")

        await browser.close()

    # Dedup i podział
    seen = set()
    unique = []
    for r in all_results:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)

    local = [r for r in unique if r["local"]]
    national = [r for r in unique if not r["local"]]

    print(f"\n=== Wyniki ===")
    print(f"Łącznie: {len(unique)}")
    print(f"Dolny Śląsk: {len(local)}")
    print(f"Cała Polska: {len(national)}")

    # Wyślij na Telegram
    msg = format_message(local, national, datetime.now().strftime("%d.%m.%Y"))
    await send_telegram(msg)

    # Zapisz JSON
    with open("results.json", "w", encoding="utf-8") as f:
        json.dump({
            "date": datetime.now().isoformat(),
            "local": local,
            "national": national,
        }, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
