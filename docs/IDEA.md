# Praelector — zamysł produktu

**Praelector** (łac. "ten, który czyta na głos") to lokalna aplikacja desktopowa, która zamienia legalnie posiadany ebook w wielogłosowy audiobook M4B. Nie jest kolejnym „wrzuć EPUB i czekaj”. Jest **warsztatem lektorskim**: przygotowuje polski tekst pod TTS, rozdziela narratora od dialogów, oznacza płeć mówców, pozwala poprawić każdą decyzję AI i dopiero potem czyta — z pauzą, resume i kontrolą VRAM.

To dokument koncepcyjny (produkt + architektura). Wymagania formalne są w `PRD.md`. Prompt dla agenta planującego implementację jest w `CODING_AGENT_PROMPT.md`.

---

## 1. Problem

Gotowe konwertery (epub2tts, Audiopub, MBook, Kokoro-epub) robią jedną rzecz: dzielą tekst na zdania i puszczają przez TTS. Dla polskiego lektora to za mało.

- Angielskie nazwiska, skróty, liczby i toponimy wychodzą jako kaleczenie.
- Dialogi z myślnika zlewają się z narracją.
- Jeden głos na 20 godzin prozy męczy.
- GPU albo stoi bezczynnie, albo wywala OOM.
- Przerwanie 4-godzinnego joba oznacza start od zera.
- Subskrypcje ChatGPT / Claude / Grok / Gemini / Cursor **nie dają klucza API** — warstwa językowa musi umieć lokalne Ollama/LM Studio _oraz_ tanie/darmowe API.

Praelector rozwiązuje **przygotowanie lektorskie**, nie tylko syntezę.

## 2. Persona v1

Jeden użytkownik: polski czytelnik z dwoma pecetami (Windows 11 + RTX 4070 Ti 12 GB; CachyOS + RX 9060 XT 16 GB), który już umie zrobić jednogłosowy audiobook i chce warsztat wielogłosowy. Produkt jest OSS od dnia pierwszego, ale v1 jest kalibrowane pod tę osobę.

## 3. Obietnica

Po wczytaniu EPUB-a użytkownik w jednym oknie:

1. widzi drzewo rozdziałów i tekst roboczy,
2. odpalą pipeline AI (lokalny lub chmurowy),
3. dostaje **listę poprawek z kategoriami** (fonetyka, dialog, płeć, śmieci konwersji, liczby…),
4. akceptuje / odrzuca / edytuje każdą,
5. przypisuje 1–3 głosy (tryb wybierany w ustawieniach),
6. nagrywa z ETA, RTF, pauzą i resume,
7. składa M4B z okładką, rozdziałami i metadanymi,
8. eksportuje „wersję dla lektora” z powrotem do EPUB.

Jedna książka naraz. Wszystko lokalnie na dysku.

## 4. Nazwa i licencja

|               |                                                                                                                   |
| ------------- | ----------------------------------------------------------------------------------------------------------------- |
| Nazwa         | **Praelector**                                                                                                    |
| Tagline       | _Prepare the page. Cast the voice._                                                                               |
| Licencja kodu | Apache License 2.0                                                                                                |
| Modele        | osobna tablica licencji w UI (Chatterbox MIT, Qwen3-TTS Apache-2.0, OmniVoice: kod Apache / wagi często CC-BY-NC) |
| Calibre       | tylko jako **opcjonalny binary** `ebook-convert` — nie linkujemy GPLv3                                            |
| DRM           | twardo odrzucamy; nie obchodzimy zabezpieczeń                                                                     |

Nie znaleziono kolizji z istniejącym produktem o tej nazwie w niszy ebook/TTS (wrzesień 2026). To nie jest opinia prawna — przed publikacją pod marką warto sprawdzić USPTO/EUIPO.

## 5. Pipeline książki

```
PDF*/MOBI/EPUB  →  roboczy EPUB
        ↓
   parser rozdziałów + czyszczenie
        ↓
   edytor lektorski (tekst + znaczniki)
        ↓
   AI prep (fonetyka, dialogi, płeć, błędy)
        ↓
   przegląd poprawek (accept / reject / edit)
        ↓
   eksport reader.epub
        ↓
   chunker TTS (zdanie / kwestia / limit modelu)
        ↓
   synteza (N workerów, limiter VRAM)
        ↓
   mux M4B + metadane + okładka
```

\*PDF tylko z warstwą tekstową. Brak OCR w v1.

### 5.1 Znaczniki w tekście roboczym

Wewnętrzny model rozdziału to nie goły string. Każdy rozdział to sekwencja **spanów**:

- `narration`
- `dialogue` + `speaker_id?` + `gender: male|female|unknown`
- `pronunciation` (forma do odczytu vs forma do wyświetlenia)
- `pause` (krótka / średnia / długa)
- `skip` (nie czytać: stopka, ISBN, numer strony)

EPUB eksportowy może zachować formy wyświetlane; EPUB „dla lektora” zawiera formy odczytu.

### 5.2 Trzy tryby głosów (ustawienie projektu)

1. **Single** — jeden głos na wszystko.
2. **Narrator + dialogue** — dwa głosy.
3. **Narrator + male + female** — trzy głosy. To tryb docelowy v1.

Brak próbki dla danego slotu = fallback na narratora z ostrzeżeniem, nie cichy fail.

## 6. Warstwa AI (przygotowanie tekstu)

AI **nie nadpisuje książki po cichu**. Zawsze powstaje `Suggestion` z kategorią, spanem źródłowym, propozycją, pewnością i możliwością ręcznej edycji.

Kategorie v1:

| Kod                   | Przykład                                      |
| --------------------- | --------------------------------------------- |
| `foreign_word`        | Walker → „Łoker”                              |
| `acronym`             | IT → „aj ti”                                  |
| `toponym`             | Washington DC → „Łoszynkton di si”            |
| `numeral`             | 238 → „dwieście trzydzieści osiem”            |
| `ordinal_heading`     | Rozdział 8 → „rozdział ósmy”                  |
| `dialogue_split`      | myślnik na początku akapitu **oraz** w środku |
| `speaker_gender`      | na podstawie „powiedział Jan” i kontekstu     |
| `conversion_artifact` | „przer-wany”, puste spacje, śmieci z PDF      |
| `dict_hit`            | słowo z listy EN znalezione w polskim tekście |

Heurystyki idą **przed** LLM: myślniki dialogowe, słownik EN, regex liczb, detekcja skrótów. LLM dostaje wąski kontekst (akapit ± sąsiednie) i ma zwrócić JSON zgodny ze schematem. Tanie/szybkie modele (Groq, Gemini Flash, lokalne 7–14B) wystarczą do klasyfikacji; trudne case’y można przepuścić przez mocniejszy profil.

### Dostawcy LLM

Aplikacja **nie instaluje** Ollamy ani LM Studio. Podłącza się do już działającego serwera.

Profile wbudowane v1:

- Ollama (`http://127.0.0.1:11434`)
- LM Studio (OpenAI-compatible localhost)
- OpenAI-compatible generic (OpenRouter, Groq, vLLM, cokolwiek)
- OpenAI oficjalne
- Anthropic
- Google Gemini
- xAI (Grok)

Klucze tylko w lokalnym magazynie OS (keyring), nigdy w repo i nigdy w logach.

Subskrypcja ChatGPT/Claude/Cursor **nie jest** API. W ustawieniach ma być krótka ściąga: darmowe/tanie startowe opcje to Groq, Google AI Studio (Gemini Flash), OpenRouter `:free`. Użytkownik może też zostać przy samym Ollama.

## 7. TTS

Wtyczki z jednym interfejsem (`synthesize(text, voice_ref, params) → wav + metrics`).

v1, działające „po instalacji” (wagi dociągane przy pierwszym użyciu, z progressem i sumą kontrolną):

| Backend                        | Po co                                                       | Licencja wag                                          |
| ------------------------------ | ----------------------------------------------------------- | ----------------------------------------------------- |
| **OmniVoice**                  | domyślny — najlepszy u pierwszego użytkownika, 600+ języków | kod Apache; wagi sprawdzać per checkpoint (często NC) |
| **Chatterbox Multilingual V3** | MIT, PL w 23 językach, klon ~5–10 s, emotion/exaggeration   | MIT                                                   |
| **Qwen3-TTS**                  | Apache-2.0, klon ~3 s, 10 języków                           | Apache-2.0                                            |

Kolejne ( CosyVoice, IndexTTS, Fish Speech ) — ten sam plugin API, nie blokują v1.

### Próbka głosu

Upload WAV/FLAC/MP3/M4A/OGG. Pipeline:

1. konwersja do PCM,
2. wyciecie ciszy (VAD),
3. normalizacja głośności (cel LUFS konfigurowalny),
4. resample do native rate modelu,
5. przycięcie do okna wymaganego przez backend (np. 5–20 s),
6. zapis profilu głosu + waveform preview + odsłuch.

Parametry: globalne (sample rate wyjścia, LUFS, fade, cisza między zdaniami) i per-model (CFG, exaggeration, steps, language id, seed…).

## 8. GPU i równoległość

Oba komputery użytkownika są first-class:

- NVIDIA CUDA (4070 Ti 12 GB)
- AMD ROCm (RX 9060 XT 16 GB)
- CPU fallback z jawnym ostrzeżeniem o RTF

Silnik przy starcie i przed jobem:

1. wykrywa vendor, VRAM total / free, driver,
2. ładuje tabelę „peak VRAM” per backend + kwantyzacja,
3. liczy `max_workers = floor((free_vram - reserve) / peak_per_worker)`,
4. `reserve` domyślnie 20% lub 1.5 GB (co większe),
5. nigdy nie startuje workera, który zepchnąłby alokację ponad limit,
6. przy skoku pamięci wstrzymuje kolejkę zamiast OOM.

Job TTS jest kolejką chunków z checkpointem na dysku. Pauza = dokończ aktualny chunk albo porzuć go atomowo (nie zapisuj pół-WAV). Resume czyta `job.json` + listę `chunks/*.wav`.

## 9. Postęp i M4B

UI joba pokazuje:

- etap (prep / review / tts / mux),
- fragment (rozdział, indeks chunka, prefiks tekstu),
- ukończone / pozostałe etapy i chunki,
- RTF (× realtime) średni i chwilowy,
- ETA,
- VRAM used / budget,
- przyciski Pause / Resume / Stop.

Skład:

- WAV/FLAC chunków → AAC w M4B (ffmpeg),
- rozdziały z TOC ebooka (edytowalne),
- metadane: tytuł, autor, lektor, rok, opis, język, okładka,
- możliwość złożyć M4B z **już nagranych** fragmentów (książka niepełna).

## 10. Architektura

```
┌─────────────────────────────────────────────┐
│  Tauri 2 + React + TypeScript (UI, i18n)    │
│  EN default, PL complete in v1              │
└──────────────────┬──────────────────────────┘
                   │ localhost HTTP + WS
┌──────────────────▼──────────────────────────┐
│  Python 3.12 sidecar (FastAPI)              │
│  ebook · suggestions · tts plugins · gpu    │
│  jobs · llm router · mux                    │
└─────────────────────────────────────────────┘
         │                         │
    Ollama / APIs              CUDA / ROCm
```

Monorepo. Sidecar startuje razem z oknem, słucha tylko `127.0.0.1`. Projekty: `~/Praelector/projects/<id>/` (konfigurowalne).

macOS: budować w CI _best effort_, bez obietnicy jakości Apple Silicon w v1 (brak maszyny do testów u maintainera).

## 11. Edytor — „pełnoprawny pod cele programu”, nie Sigil

Musi:

- drzewo rozdziałów (rename, merge, split, reorder, include/exclude z odczytu),
- edycja tekstu rozdziału,
- podświetlanie spanów (dialog, wymowa, skip),
- panel sugestii z filtrem kategorii i accept/reject/edit,
- znajdź/zamień,
- podgląd „jak usłyszy lektor” vs „jak wygląda w książce”,
- zapis projektu i eksport EPUB.

Nie musi: pełny CSS EPUB, przypisy pop-up, layout fixed-page, edycja okładek wektorowych.

## 12. Open source i automatyzacja GH

Cel użytkownika: wejść na GitHub, przeczytać PR, merge gdy CI zielone.

- Conventional Commits
- szablony Issue/PR
- CI: lint + unit + (w miarę) integracja; build Win/Linux
- Release Please / Changesets → tag + changelog + draft release
- agent (Cursor / Codex / Copilot) otwiera PR, **człowiek merguje**
- docs po angielsku (`docs/`), UI EN+PL

Nie automatyzujemy pusha na `main` bez review.

## 13. Świadomie poza v1

- OCR skanów PDF
- obchodzenie DRM
- instalator Ollamy / pobieranie LLM-ów czatu
- kolejka wielu książek
- chmura / sync projektów
- pełny WYSIWYG jak Calibre Editor
- gwarantowany macOS
- głosy per _postać_ (tylko płeć + narrator w v1)
- Fine-tuning TTS

## 14. Definicja sukcesu v1

Użytkownik wczytuje polską powieść EPUB, dostaje poprawnie pocięte dialogi z płcią, poprawia listę fonetyzacji, nagrywa trzema głosami na 4070 Ti albo 9060 XT, pauzuje na noc, wznawia rano, wychodzi z M4B z rozdziałami i okładką oraz EPUB-em „dla lektora”.
