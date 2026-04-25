# Monitor Przetargów Foto/Wideo

Automatyczny monitoring przetargów na usługi fotograficzne i wideo.
Sprawdza co 2 dni:
- platformazakupowa.pl
- bazakonkurencyjnosci.funduszeeuropejskie.gov.pl

Wysyła wyniki na Telegram. Działa w chmurze GitHub Actions — bez Twojego komputera.

## Setup (15 minut, jednorazowo)

### Krok 1 — Stwórz Bota Telegram

1. Otwórz Telegram → napisz do `@BotFather`
2. `/newbot` → podaj nazwę i username
3. Skopiuj **token** (np. `1234567:AAFxyz...`)
4. Napisz `/start` do swojego nowego bota
5. Otwórz: `https://api.telegram.org/botTWOJ_TOKEN/getUpdates`
6. Skopiuj `chat.id` (liczba)

### Krok 2 — Stwórz repozytorium GitHub

1. Wejdź na https://github.com/new
2. Nazwa: `przetargi-monitor` → Private (prywatne!)
3. Create repository

### Krok 3 — Wgraj pliki

Wgraj wszystkie pliki z tego ZIP do repozytorium:
- `monitor.py`
- `requirements.txt`
- `.github/workflows/monitor.yml`
- `README.md`

### Krok 4 — Dodaj sekrety (BARDZO WAŻNE)

W repozytorium → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Dodaj te sekrety:

| Nazwa | Wartość |
|-------|---------|
| `TELEGRAM_TOKEN` | token bota z BotFather |
| `TELEGRAM_CHAT_ID` | Twoje chat_id |
| `PLATFORMA_LOGIN` | login do platformazakupowa.pl |
| `PLATFORMA_HASLO` | hasło do platformazakupowa.pl |
| `BAZA_LOGIN` | login do Bazy Konkurencyjności |
| `BAZA_HASLO` | hasło do Bazy Konkurencyjności |

### Krok 5 — Uruchom test

1. W repo → zakładka **Actions**
2. Po lewej: **Monitor Przetargów** → **Run workflow** → Run
3. Zobacz logi (klikając na uruchomiony job)
4. Sprawdź Telegram — powinieneś dostać wiadomość

## Harmonogram

Skrypt uruchamia się automatycznie **co 2 dni o 10:00 czasu polskiego**.

Możesz też uruchomić ręcznie w dowolnym momencie:
**Actions** → **Monitor Przetargów** → **Run workflow**

## Modyfikacje

### Zmiana częstotliwości
Edytuj `.github/workflows/monitor.yml`, linia z `cron`:
- `'0 8 */2 * *'` — co 2 dni
- `'0 8 * * *'` — codziennie
- `'0 8 * * 1,4'` — pon i czw

### Zmiana słów kluczowych
Edytuj `monitor.py`, listy `KEYWORDS` i `LOCAL_KEYWORDS`.

## Koszty

GitHub Actions daje 2000 minut/miesiąc za darmo na prywatne repo.
Każde uruchomienie ~3 minuty = ~45 minut/miesiąc. Bez problemu się mieści.

Telegram bot — bezpłatny.
