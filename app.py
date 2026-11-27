"""A small local English/Faeric translator backed by SQLite."""

import csv
import io
import os
import re
import sqlite3
import unicodedata
from pathlib import Path

from flask import Flask, abort, g, jsonify, redirect, render_template, request, url_for


ROOT = Path(__file__).resolve().parent
DATABASE = Path(
    os.environ.get("FAERIC_DATABASE", ROOT / "instance" / "faeric.sqlite3")
).expanduser().resolve()
TOKEN_RE = re.compile(r"\w+|[^\w\s]+|\s+", re.UNICODE)
ENGLISH_POSSESSIVE_RE = re.compile(
    r"(?P<owner>\b[\w-]+)(?:\x27|\u2019)s(?P<space>\s+)(?P<owned>[\w-]+)", re.UNICODE
)
NON_POSSESSIVE_CONTRACTION_OWNERS = {
    "he", "how", "it", "let", "she", "that", "there", "they", "we", "what",
    "when", "where", "which", "who", "why", "you",
}
MAX_TEXT_LENGTH = 500
LEXICON_PAGE_SIZE = 50
LEXICON_LOOKUP_BATCH_SIZE = 500

# Transcribed from sources/Fae Rune Pronunciation Guide and Dictionary.docx.
# The Faeric spellings are the document's Latin-keyboard rune transcriptions.
SOURCE_LEXICON = [
    ("light", "t", "rune meaning", "Trye", "Rune name; also life and joy"),
    ("life", "t", "rune meaning", "Trye", "Rune name; also light and joy"),
    ("joy", "t", "rune meaning", "Trye", "Rune name; also light and life"),
    ("sun", "d", "rune meaning", "Drye", "Rune name"),
    ("heat", "f", "rune meaning", "Frey", "Rune name"),
    ("fire", "v", "rune meaning", "Vey", "Rune name"),
    ("air", "i", "rune meaning", "Ave", "Rune name"),
    ("cloud", "e", "rune meaning", "Eve", "Rune name"),
    ("water", "w", "rune meaning", "Uan", "Rune name"),
    ("rain", "W", "rune meaning", "Uan", "Rune name"),
    ("earth", "R", "rune meaning", "T’r", "Rune name"),
    ("stone", "R", "rune meaning", "T’r", "Rune name"),
    ("lava", "A", "rune meaning", "Aine", "Rune name"),
    ("lightning", "L", "rune meaning", "L’v", "Rune name"),
    ("cold", "s", "rune meaning", "Syle", "Rune name"),
    ("ice", "Z", "rune meaning", "Zyle", "Rune name"),
    ("plant", "p", "rune meaning", "Pl’v", "Rune name"),
    ("wood", "B", "rune meaning", "Bl’v", "Rune name"),
    ("dark", "k", "rune meaning", "Kor", "Rune name; also death and misery"),
    ("death", "k", "rune meaning", "Kor", "Rune name; also dark and misery"),
    ("misery", "k", "rune meaning", "Kor", "Rune name; also dark and death"),
    ("moon", "K", "rune meaning", "Kor", "Rune name"),
    ("yet", "G", "rune meaning", "Gyur", "Rune name"),
    ("and", "H", "rune meaning", "Yhol", "Rune name"),
    ("to", "j", "rune meaning", "Jhu", "Rune name"),
    ("from", "J", "rune meaning", "Zhu", "Rune name; also of"),
    ("of", "J", "rune meaning", "Zhu", "Rune name; also from"),
    ("or", "n", "rune meaning", "Nur", "Rune name"),
    ("nor", "m", "rune meaning", "Mur", "Rune name"),
    ("so", "u", "rune meaning", "Urd", "Rune name"),
    ("but", "O", "rune meaning", "Ord", "Rune name"),
    ("for", "y", "rune meaning", "Yere", "Rune name"),
    ("I", "ni", "pronoun", "Nai", ""),
    ("you", "uz", "pronoun", "Uze", "Singular, very informal"),
    ("you", "us", "pronoun", "Usse", "Singular, informal"),
    ("you", "nu", "pronoun", "nu", "Singular, neutral"),
    ("you", "on", "pronoun", "Ohn", "Singular, formal"),
    ("you", "Om", "pronoun", "Ome", "Singular, very formal"),
    ("he", "ki", "pronoun", "Kai", "Singular"),
    ("they (singular)", "ki", "pronoun", "Kai", "Singular"),
    ("she", "dki", "pronoun", "D’kai", ""),
    ("we", "nam", "pronoun", "Naym", ""),
    ("you", "urz", "pronoun", "Urz", "Plural, very informal"),
    ("you", "urs", "pronoun", "Urs", "Plural, informal"),
    ("you", "ur", "pronoun", "Ur", "Plural, neutral"),
    ("you", "orn", "pronoun", "Orn", "Plural, formal"),
    ("you", "Orm", "pronoun", "Orm", "Plural, very formal"),
    ("they", "kar", "pronoun", "Kayr", "Plural"),
    ("happy", "fl", "adjective", "F’l", ""),
    ("sad", "tres", "adjective", "Trese", ""),
    ("angry", "fre", "adjective", "F’ree", ""),
    ("worried", "Oku", "adjective", "Oku", ""),
    ("good", "Bn", "adjective", "B’n", ""),
    ("okay", "pn", "adjective", "P’n", ""),
    ("bad", "nl", "adjective", "N’l", ""),
    ("tired", "ts", "adjective", "T’s", ""),
    ("awake", "pr", "adjective", "P’r", ""),
    ("travel", "jhJvihar", "verb", "Vy’hare", "Source gloss: to and from/travel"),
    ("seal", "ziyar", "verb", "Ziyare", ""),
    ("circle", "Serklar", "verb", "Seerklare", ""),
    ("hold", "kdar", "verb", "K’dare", ""),
    ("protect", "Proter", "verb", "Protere", ""),
    ("who", "not", "question word", "Note", ""),
    ("what", "nod", "question word", "Node", ""),
    ("when", "tki", "question word", "Tkai", ""),
    ("where", "pri", "question word", "P’rai", ""),
    ("why", "ynod", "question word", "Y’node", ""),
    ("how", "jorn", "question word", "Jor’n", ""),
    ("which", "nin", "question word", "Naiy’n", ""),
    ("with", "hun", "preposition", "H’un", ""),
    ("without", "hum", "preposition", "H’um", ""),
    ("not", "km", "negation", "K’m", ""),
    ("yes", "hi", "answer", "Hai", ""),
    ("no", "Mai", "answer", "Mai", ""),
    ("hello", "hol", "greeting", "Hol", ""),
    ("goodbye", "Nteo", "greeting", "‘Nteo", ""),
    ("friend", "Mego", "noun", "Mego", ""),
]

SOURCE_CONJUGATIONS = [
    ("present", "u", "", "Present = u + pronoun + verb"),
    ("past", "", "n", "Past = pronoun + verb + n"),
    ("future", "", "m", "Future = pronoun + verb + m"),
]
# In compounds/affixes, a rune contributes its phonetic sound. A standalone
# rune used as a word instead uses that rune's name from its lexicon entry.
RUNE_PRONUNCIATIONS = {
    "t": "t", "d": "d", "f": "f", "v": "v", "i": "e͡ɪ", "e": "iː",
    "w": "w", "W": "w", "R": "ɹ", "A": "a͡ɪ", "L": "l", "s": "s", "Z": "z",
    "p": "p", "B": "b", "k": "k", "K": "k", "G": "g", "H": "h",
    "j": "d͡ʒ", "J": "d͡ʒ", "n": "n", "m": "m", "u": "u",
    "O": "o͡ʊ", "y": "j",
}
IRREGULAR_PAST_FORMS = {"hold": "held"}

app = Flask(__name__)
IS_PRODUCTION = os.environ.get("APP_ENV", "development").casefold() == "production"
SECRET_KEY = os.environ.get("SECRET_KEY")
if IS_PRODUCTION and not SECRET_KEY:
    raise RuntimeError("Set SECRET_KEY in the production environment before starting the app.")
app.config.update(
    DATABASE=DATABASE,
    SECRET_KEY=SECRET_KEY or "local-development-only",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=IS_PRODUCTION,
)


def normalize_english(value):
    return unicodedata.normalize("NFC", value).casefold()


def normalize_faeric(value):
    # Upper/lowercase Latin keys select different glyphs in the supplied rune font.
    return unicodedata.normalize("NFC", value)


def connect_db():
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(app.config["DATABASE"])
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def get_db():
    if "db" not in g:
        g.db = connect_db()
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.get("/health")
def health():
    """Lightweight readiness endpoint for a hosting platform's health probe."""
    get_db().execute("SELECT 1")
    return jsonify(status="ok")


def initialize_db():
    db = connect_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS languages (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS app_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS lexicon_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            english TEXT NOT NULL,
            faeric TEXT NOT NULL,
            english_norm TEXT NOT NULL,
            faeric_norm TEXT NOT NULL,
            part_of_speech TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            pronunciation TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS language_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL DEFAULT 'suffix',
            name TEXT NOT NULL,
            source_suffix TEXT NOT NULL DEFAULT '',
            target_suffix TEXT NOT NULL DEFAULT '',
            tense TEXT NOT NULL DEFAULT '',
            prefix TEXT NOT NULL DEFAULT '',
            suffix TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1))
        );

        CREATE TABLE IF NOT EXISTS translation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_language TEXT NOT NULL REFERENCES languages(code),
            target_language TEXT NOT NULL REFERENCES languages(code),
            original_text TEXT NOT NULL,
            translated_text TEXT NOT NULL,
            pronunciation_text TEXT NOT NULL DEFAULT '',
            unknown_words TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_history_created
            ON translation_history(created_at DESC);
        """
    )

    # Upgrade databases created by the first starter version. It required every
    # English and Faeric spelling to be unique, so only duplicate pairs are barred.
    lexicon_columns = {row["name"] for row in db.execute("PRAGMA table_info(lexicon_entries)")}
    if "pronunciation" not in lexicon_columns:
        db.execute(
            "ALTER TABLE lexicon_entries ADD COLUMN pronunciation TEXT NOT NULL DEFAULT ''"
        )
    single_value_unique = set()
    for index in db.execute("PRAGMA index_list(lexicon_entries)"):
        if index["unique"]:
            indexed_columns = tuple(
                row["name"] for row in db.execute(f"PRAGMA index_info('{index['name']}')")
            )
            if indexed_columns in {("english_norm",), ("faeric_norm",)}:
                single_value_unique.add(indexed_columns)
    if single_value_unique:
        db.execute(
            """CREATE TABLE lexicon_entries_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                english TEXT NOT NULL,
                faeric TEXT NOT NULL,
                english_norm TEXT NOT NULL,
                faeric_norm TEXT NOT NULL,
                part_of_speech TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                pronunciation TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        db.execute(
            """INSERT OR IGNORE INTO lexicon_entries_new
               (id, english, faeric, english_norm, faeric_norm, part_of_speech,
                notes, pronunciation, created_at)
               SELECT id, english, faeric, english_norm, faeric_norm, part_of_speech,
                      notes, pronunciation, created_at
               FROM lexicon_entries"""
        )
        db.execute("DROP TABLE lexicon_entries")
        db.execute("ALTER TABLE lexicon_entries_new RENAME TO lexicon_entries")
    normalization_version = db.execute(
        "SELECT value FROM app_metadata WHERE key = 'lexicon_normalization_version'"
    ).fetchone()
    if normalization_version is None or normalization_version["value"] != "2":
        last_id = 0
        while True:
            batch = db.execute(
                "SELECT id, english, faeric FROM lexicon_entries "
                "WHERE id > ? ORDER BY id LIMIT 2000",
                (last_id,),
            ).fetchall()
            if not batch:
                break
            db.executemany(
                "UPDATE lexicon_entries SET english_norm = ?, faeric_norm = ? WHERE id = ?",
                [
                    (normalize_english(row["english"]), normalize_faeric(row["faeric"]), row["id"])
                    for row in batch
                ],
            )
            last_id = batch[-1]["id"]
        db.execute(
            "INSERT OR REPLACE INTO app_metadata(key, value) "
            "VALUES ('lexicon_normalization_version', '2')"
        )
    # Update the original source entry in databases initialized before the user
    # changed the Faeric form for "no" from ni / Nai to Mai.
    db.execute(
        """UPDATE lexicon_entries
           SET faeric = 'Mai', faeric_norm = 'Mai', pronunciation = 'Mai', notes = ''
           WHERE english_norm = 'no' AND faeric_norm = 'ni'
             AND part_of_speech = 'answer'"""
    )
    # Single runes used as whole words are pronounced by rune name. Their
    # phonetic values remain in RUNE_PRONUNCIATIONS for use inside compounds.
    for english, faeric, pos, pronunciation, notes in SOURCE_LEXICON:
        if pos == "rune meaning" and len(faeric) == 1 and pronunciation:
            db.execute(
                """UPDATE lexicon_entries SET pronunciation = ?, notes = ?
                   WHERE english_norm = ? AND faeric_norm = ? AND part_of_speech = ?""",
                (pronunciation, notes, normalize_english(english), normalize_faeric(faeric), pos),
            )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_lexicon_pair "
        "ON lexicon_entries(english_norm, faeric_norm)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_lexicon_english_norm "
        "ON lexicon_entries(english_norm, id)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_lexicon_faeric_norm "
        "ON lexicon_entries(faeric_norm, id)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_lexicon_pos_faeric "
        "ON lexicon_entries(part_of_speech, faeric_norm)"
    )

    rule_columns = {row["name"] for row in db.execute("PRAGMA table_info(language_rules)")}
    for column, declaration in (
        ("kind", "TEXT NOT NULL DEFAULT 'suffix'"),
        ("tense", "TEXT NOT NULL DEFAULT ''"),
        ("prefix", "TEXT NOT NULL DEFAULT ''"),
        ("suffix", "TEXT NOT NULL DEFAULT ''"),
    ):
        if column not in rule_columns:
            db.execute(f"ALTER TABLE language_rules ADD COLUMN {column} {declaration}")

    history_columns = {row["name"] for row in db.execute("PRAGMA table_info(translation_history)")}
    if "pronunciation_text" not in history_columns:
        db.execute(
            "ALTER TABLE translation_history ADD COLUMN pronunciation_text "
            "TEXT NOT NULL DEFAULT ''"
        )

    db.executemany(
        "INSERT OR IGNORE INTO languages (code, name) VALUES (?, ?)",
        [("en", "English"), ("fae", "Faeric")],
    )
    db.executemany(
        """INSERT OR IGNORE INTO lexicon_entries
           (english, faeric, english_norm, faeric_norm, part_of_speech, notes, pronunciation)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            (english, faeric, normalize_english(english), normalize_faeric(faeric), pos, notes, pronunciation)
            for english, faeric, pos, pronunciation, notes in SOURCE_LEXICON
        ],
    )
    for tense, prefix, suffix, description in SOURCE_CONJUGATIONS:
        db.execute(
            """INSERT INTO language_rules
               (kind, name, source_suffix, target_suffix, tense, prefix, suffix, description)
               SELECT 'conjugation', ?, '', '', ?, ?, ?, ?
               WHERE NOT EXISTS (
                   SELECT 1 FROM language_rules WHERE kind = 'conjugation' AND tense = ?
               )""",
            (tense.title(), tense, prefix, suffix, description, tense),
        )
    db.execute(
        "INSERT OR IGNORE INTO app_metadata(key, value) "
        "SELECT 'lexicon_entry_count', CAST(COUNT(*) AS TEXT) FROM lexicon_entries"
    )
    db.commit()
    db.close()


def english_verb_form(lemma, tense):
    if tense == "past":
        if lemma in IRREGULAR_PAST_FORMS:
            return IRREGULAR_PAST_FORMS[lemma]
        if lemma.endswith("e"):
            return lemma + "d"
        if len(lemma) > 1 and lemma.endswith("y") and lemma[-2] not in "aeiou":
            return lemma[:-1] + "ied"
        return lemma + "ed"
    if tense == "future":
        return "will " + lemma
    return lemma


def find_english_verb(word, verb_entries, allow_past=False):
    normalized = word.casefold()
    for row in verb_entries:
        if normalized == row["english_norm"]:
            return row, "present"
    if allow_past and normalized.endswith("s"):
        present_candidates = [normalized[:-1]]
        if normalized.endswith("es"):
            present_candidates.append(normalized[:-2])
        for candidate in present_candidates:
            for row in verb_entries:
                if candidate == row["english_norm"]:
                    return row, "present"
    if allow_past:
        for lemma, past_form in IRREGULAR_PAST_FORMS.items():
            if normalized == past_form:
                match = next((row for row in verb_entries if row["english_norm"] == lemma), None)
                if match is not None:
                    return match, "past"
    if allow_past and normalized.endswith("ed"):
        candidates = [normalized[:-2], normalized[:-2] + "e", normalized[:-1]]
        if len(candidates[0]) > 1 and candidates[0][-1] == candidates[0][-2]:
            candidates.append(candidates[0][:-1])
        if candidates[0].endswith("i"):
            candidates.append(candidates[0][:-1] + "y")
        for candidate in candidates:
            for row in verb_entries:
                if candidate == row["english_norm"]:
                    return row, "past"
    return None, None


def english_verb_lookup_candidates(word):
    """Return likely English lemmas needed to recognize common inflections."""
    normalized = normalize_english(word)
    candidates = {normalized}
    if normalized.endswith("s"):
        candidates.add(normalized[:-1])
        if normalized.endswith("es"):
            candidates.add(normalized[:-2])
    for lemma, past_form in IRREGULAR_PAST_FORMS.items():
        if normalized == past_form:
            candidates.add(lemma)
    if normalized.endswith("ed"):
        stem = normalized[:-2]
        candidates.update((stem, stem + "e", normalized[:-1]))
        if len(stem) > 1 and stem[-1] == stem[-2]:
            candidates.add(stem[:-1])
        if stem.endswith("i"):
            candidates.add(stem[:-1] + "y")
    return candidates


def rewrite_english_possessives(text):
    """Turn simple English ``owner's noun`` forms into ``the noun of owner``."""
    def reorder(match):
        owner = match.group("owner")
        if owner.casefold() in NON_POSSESSIVE_CONTRACTION_OWNERS:
            return match.group(0)
        return f"the {match.group('owned')} of {owner}"

    return ENGLISH_POSSESSIVE_RE.sub(reorder, text)


def candidate_lexicon_keys(text, direction, rules):
    """Build bounded lookup keys from the input, including possible phrases."""
    pieces = TOKEN_RE.findall(text)
    word_positions = [index for index, piece in enumerate(pieces) if piece.isalnum()]
    normalize = normalize_english if direction == "en_to_fae" else normalize_faeric
    keys = set()

    for position_index, start in enumerate(word_positions):
        word = pieces[start]
        normalized_word = normalize(word)
        keys.add(normalized_word)

        if direction == "en_to_fae":
            keys.update(english_verb_lookup_candidates(word))

        for rule in rules:
            source_suffix = (
                rule["source_suffix"] if direction == "en_to_fae" else rule["target_suffix"]
            )
            suffix = normalize(source_suffix)
            if suffix and normalized_word.endswith(suffix) and len(normalized_word) > len(suffix):
                keys.add(normalized_word[:-len(suffix)])

        # Dictionary entries may be words or phrases. Candidate phrases are
        # drawn only from the submitted text, never from the whole lexicon.
        for end in word_positions[position_index:]:
            phrase = "".join(pieces[start:end + 1])
            if len(phrase) > 120:
                break
            keys.add(normalize(phrase))

    return keys


def fetch_lexicon_entries(db, field, keys):
    """Fetch only indexed lexicon keys present in this translation request."""
    if field not in {"english_norm", "faeric_norm"}:
        raise ValueError("Unsupported lexicon lookup field")
    rows_by_id = {}
    key_list = list(keys)
    for start in range(0, len(key_list), LEXICON_LOOKUP_BATCH_SIZE):
        batch = key_list[start:start + LEXICON_LOOKUP_BATCH_SIZE]
        placeholders = ",".join("?" for _ in batch)
        query = f"SELECT * FROM lexicon_entries WHERE {field} IN ({placeholders}) ORDER BY id"
        for row in db.execute(query, batch):
            rows_by_id[row["id"]] = row
    return sorted(rows_by_id.values(), key=lambda row: row["id"])


def lookup_entries_for_translation(db, text, direction, rules, conjugations):
    """Look up matching words and phrases without loading the full dictionary."""
    field = "english_norm" if direction == "en_to_fae" else "faeric_norm"
    keys = candidate_lexicon_keys(text, direction, rules)

    pronouns = []
    if direction == "fae_to_en":
        # Pronoun forms are needed to split fused Faeric conjugations into their
        # pronoun and verb parts. This is a small indexed category, not the lexicon.
        pronouns = db.execute(
            "SELECT * FROM lexicon_entries WHERE part_of_speech = 'pronoun'"
        ).fetchall()
        pieces = TOKEN_RE.findall(text)
        for piece in pieces:
            if not piece.isalnum():
                continue
            normalized = normalize_faeric(piece)
            for pronoun in pronouns:
                for rule in conjugations:
                    prefix = normalize_faeric(rule["prefix"] + pronoun["faeric"])
                    suffix = normalize_faeric(rule["suffix"])
                    if normalized.startswith(prefix) and (not suffix or normalized.endswith(suffix)):
                        suffix_length = len(suffix) if suffix else 0
                        end = len(normalized) - suffix_length if suffix_length else len(normalized)
                        verb_key = normalized[len(prefix):end]
                        if verb_key:
                            keys.add(verb_key)

    entries = fetch_lexicon_entries(db, field, keys)
    if pronouns:
        found_ids = {row["id"] for row in entries}
        entries.extend(row for row in pronouns if row["id"] not in found_ids)
    return entries


def preferred_entry(rows, direction):
    candidates = [row for row in rows if row["part_of_speech"] == "pronoun"]
    if not candidates:
        return rows[0]
    # "you" has several politeness and number variants. Use the documented
    # neutral singular form as the default when translating from English.
    if direction == "en_to_fae":
        neutral = [row for row in candidates if "singular, neutral" in row["notes"].casefold()]
        if neutral:
            return neutral[0]
    return candidates[0]


def preferred_pronoun(rows, direction):
    target_field = "faeric" if direction == "en_to_fae" else "english"
    return preferred_entry(rows, direction)[target_field]


def pronunciation_for_affix(value):
    return "".join(RUNE_PRONUNCIATIONS.get(char) or char for char in value)


def pronunciation_for_word(entry, fallback):
    if len(entry["faeric"]) == 1:
        return entry["pronunciation"] or "[rune name not set]"
    return entry["pronunciation"] or pronunciation_for_affix(entry["faeric"]) or fallback


def pronunciation_for_component(entry):
    if len(entry["faeric"]) == 1:
        return pronunciation_for_affix(entry["faeric"])
    return entry["pronunciation"] or entry["faeric"]


def cache_english_verb_forms(db, text, entries, conjugations):
    """Create missing standalone past/future forms from dictionary verb lemmas."""
    words = {}
    for row in entries:
        words.setdefault(row["english_norm"], []).append(row)
    verb_entries = [row for row in entries if row["part_of_speech"] == "verb"]
    if not verb_entries:
        return entries

    rules_by_tense = {rule["tense"]: rule for rule in conjugations}
    raw_pieces = TOKEN_RE.findall(text)

    def cache_form(english_form, verb, tense):
        rule = rules_by_tense.get(tense)
        if rule is None or not (rule["prefix"] or rule["suffix"]):
            return
        faeric_form = rule["prefix"] + verb["faeric"] + rule["suffix"]
        english_norm = normalize_english(english_form)
        faeric_norm = normalize_faeric(faeric_form)
        if english_norm in words:
            return

        pronunciation = (
            pronunciation_for_affix(rule["prefix"])
            + pronunciation_for_component(verb)
            + pronunciation_for_affix(rule["suffix"])
        ).lower()
        before = db.total_changes
        db.execute(
            """INSERT OR IGNORE INTO lexicon_entries
               (english, faeric, english_norm, faeric_norm, part_of_speech, notes, pronunciation)
               VALUES (?, ?, ?, ?, 'verb form', ?, ?)""",
            (
                english_form, faeric_form, english_norm, faeric_norm,
                f"Generated {tense} form of {verb['english']}", pronunciation,
            ),
        )
        if db.total_changes > before:
            db.execute(
                "UPDATE app_metadata SET value = "
                "CAST(CAST(value AS INTEGER) + 1 AS TEXT) "
                "WHERE key = 'lexicon_entry_count'"
            )
        generated = db.execute(
            "SELECT * FROM lexicon_entries WHERE english_norm = ? AND faeric_norm = ?",
            (english_norm, faeric_norm),
        ).fetchone()
        if generated is not None:
            entries.append(generated)
            words.setdefault(english_norm, []).append(generated)

    for index, piece in enumerate(raw_pieces):
        if not piece.isalnum():
            continue
        normalized = normalize_english(piece)
        if normalized not in words:
            verb, tense = find_english_verb(piece, verb_entries, allow_past=True)
            if verb is not None and tense == "past":
                cache_form(piece, verb, "past")

        if normalized != "will":
            continue
        next_index = index + 1
        while next_index < len(raw_pieces) and raw_pieces[next_index].isspace():
            next_index += 1
        if next_index >= len(raw_pieces) or not raw_pieces[next_index].isalnum():
            continue
        english_form = "".join(raw_pieces[index:next_index + 1])
        if normalize_english(english_form) in words:
            continue
        verb, _ = find_english_verb(raw_pieces[next_index], verb_entries)
        if verb is not None:
            cache_form(english_form, verb, "future")

    return entries


def translate_text(text, direction, entries, rules, conjugations):
    """Translate vocabulary and apply configured affix and conjugation rules."""
    forward = direction == "en_to_fae"
    source_key = "english_norm" if forward else "faeric_norm"
    target_key = "faeric" if forward else "english"
    words = {}
    for row in entries:
        words.setdefault(row[source_key], []).append(row)
    verb_entries = [row for row in entries if row["part_of_speech"] == "verb"]
    pronoun_entries = [row for row in entries if row["part_of_speech"] == "pronoun"]
    translated = []
    pronunciation_pieces = []
    unknown = []

    if forward:
        # Apply the source document's pronoun + verb conjugation to simple
        # English subject/verb phrases. English past and "will" are recognized.
        raw_pieces = TOKEN_RE.findall(text)
        index = 0
        generated_forms = set()
        generated_pronunciations = {}
        while index < len(raw_pieces):
            piece = raw_pieces[index]
            pronouns = words.get(normalize_english(piece), []) if piece.isalnum() else []
            pronoun = next((row for row in pronouns if row["part_of_speech"] == "pronoun"), None)
            if pronoun is not None:
                j = index + 1
                while j < len(raw_pieces) and raw_pieces[j].isspace():
                    j += 1
                tense = "present"
                if j < len(raw_pieces) and raw_pieces[j].casefold() == "will":
                    tense = "future"
                    j += 1
                    while j < len(raw_pieces) and raw_pieces[j].isspace():
                        j += 1
                if j < len(raw_pieces) and raw_pieces[j].isalnum():
                    verb, detected_tense = find_english_verb(
                        raw_pieces[j], verb_entries, allow_past=(tense == "present")
                    )
                    if verb is not None:
                        if tense == "present":
                            tense = detected_tense
                        conjugation = next(
                            (rule for rule in conjugations if rule["tense"] == tense), None
                        )
                        if conjugation is not None:
                            pronoun_entry = preferred_entry(pronouns, direction)
                            faeric_pronoun = pronoun_entry["faeric"]
                            form = (
                                conjugation["prefix"]
                                + faeric_pronoun
                                + verb["faeric"]
                                + conjugation["suffix"]
                            )
                            translated.append(form)
                            form_key = normalize_faeric(form)
                            generated_forms.add(form_key)
                            pronunciation_parts = []
                            if conjugation["prefix"]:
                                pronunciation_parts.append(
                                    pronunciation_for_affix(conjugation["prefix"])
                                )
                            pronunciation_parts.append(
                                pronunciation_for_component(pronoun_entry)
                            )
                            pronunciation_parts.append(pronunciation_for_component(verb))
                            if conjugation["suffix"]:
                                pronunciation_parts.append(
                                    pronunciation_for_affix(conjugation["suffix"])
                                )
                            generated_pronunciations[form_key] = "".join(pronunciation_parts).lower()
                            index = j + 1
                            continue
            translated.append(piece)
            index += 1
        raw_pieces = translated
        translated = []
        # Preserve conjugated Faeric forms during the ordinary vocabulary pass.
        conjugated_forms = generated_forms
    else:
        raw_pieces = TOKEN_RE.findall(text)
        conjugated_forms = {}
        # Recognize the source conjugation templates in reverse.
        for piece in raw_pieces:
            if not piece.isalnum():
                continue
            normalized = normalize_faeric(piece)
            for pronoun in pronoun_entries:
                for verb in verb_entries:
                    for rule in conjugations:
                        form = (
                            rule["prefix"]
                            + pronoun["faeric"]
                            + verb["faeric"]
                            + rule["suffix"]
                        )
                        form = normalize_faeric(form)
                        if normalized == form:
                            english_verb = english_verb_form(verb["english"], rule["tense"])
                            conjugated_forms[normalized] = pronoun["english"] + " " + english_verb
                            break
                    if normalized in conjugated_forms:
                        break
                if normalized in conjugated_forms:
                    break

    # Match saved multiword entries before tokenizing the remaining text.
    source_text = "".join(raw_pieces)
    phrase_keys = sorted((key for key in words if re.search(r"\s", key)), key=len, reverse=True)
    if phrase_keys:
        phrase_pattern = re.compile(
            r"(?<!\w)(" + "|".join(re.escape(key) for key in phrase_keys) + r")(?!\w)",
            re.IGNORECASE if forward else 0,
        )
        pieces = []
        for part in phrase_pattern.split(source_text):
            if (normalize_english(part) if forward else normalize_faeric(part)) in words:
                pieces.append(part)
            else:
                pieces.extend(TOKEN_RE.findall(part))
    else:
        pieces = TOKEN_RE.findall(source_text)

    for piece_index, piece in enumerate(pieces):
        if not piece or piece.isspace() or not any(char.isalnum() for char in piece):
            translated.append(piece)
            if forward:
                pronunciation_pieces.append(piece)
            continue

        normalized = normalize_english(piece) if forward else normalize_faeric(piece)
        if forward and normalize_faeric(piece) in conjugated_forms:
            translated.append(piece)
            pronunciation_pieces.append(
                generated_pronunciations.get(normalize_faeric(piece), piece)
            )
            continue
        if not forward and normalized in conjugated_forms:
            translated.append(conjugated_forms[normalized])
            continue
        candidates = words.get(normalized, [])
        result = None
        result_pronunciation = None
        if candidates:
            if forward:
                chosen = preferred_entry(candidates, direction)
                result = chosen[target_key]
                result_pronunciation = pronunciation_for_word(chosen, result)
            else:
                # Keep real homonyms visible instead of silently choosing one.
                result = " / ".join(dict.fromkeys(row[target_key] for row in candidates))
        if result is None:
            for rule in rules:
                in_suffix = rule["source_suffix"] if forward else rule["target_suffix"]
                out_suffix = rule["target_suffix"] if forward else rule["source_suffix"]
                in_suffix = normalize_english(in_suffix) if forward else normalize_faeric(in_suffix)
                if in_suffix and normalized.endswith(in_suffix) and len(normalized) > len(in_suffix):
                    stem = normalized[: -len(in_suffix)]
                    stem_rows = words.get(stem)
                    if stem_rows:
                        chosen = preferred_entry(stem_rows, direction)
                        stem_translation = chosen[target_key]
                        result = stem_translation + out_suffix
                        if forward:
                            pronunciation_parts = [pronunciation_for_component(chosen)]
                            if out_suffix:
                                pronunciation_parts.append(pronunciation_for_affix(out_suffix))
                            result_pronunciation = " ".join(pronunciation_parts)
                        break
        if result is None:
            translated.append(piece)
            unknown.append(piece)
            if forward:
                pronunciation_pieces.append(piece)
        else:
            translated.append(result)
            if forward:
                pronunciation_pieces.append(result_pronunciation or result)

    pronunciation = "".join(pronunciation_pieces) if forward else ""
    return "".join(translated), list(dict.fromkeys(unknown)), pronunciation


def page_data():
    db = get_db()
    entry_count = db.execute(
        "SELECT value FROM app_metadata WHERE key = 'lexicon_entry_count'"
    ).fetchone()
    return {
        "entry_count": int(entry_count["value"]) if entry_count else 0,
        "rule_count": db.execute(
            "SELECT COUNT(*) FROM language_rules WHERE enabled = 1"
        ).fetchone()[0],
    }


def prefix_upper_bound(prefix):
    """Return the exclusive Unicode sort bound for a BINARY prefix range."""
    characters = list(prefix)
    for index in range(len(characters) - 1, -1, -1):
        codepoint = ord(characters[index])
        if codepoint < 0x10FFFF:
            next_codepoint = codepoint + 1
            if 0xD800 <= next_codepoint <= 0xDFFF:
                next_codepoint = 0xE000
            return "".join(characters[:index]) + chr(next_codepoint)
    return None


@app.route("/", methods=["GET", "POST"])
def translate():
    db = get_db()
    result = None
    pronunciation = None
    unknown_words = []
    message = None
    original = ""
    direction = "en_to_fae"

    if request.method == "POST":
        original = request.form.get("text", "").strip()
        direction = request.form.get("direction", "en_to_fae")
        if direction not in {"en_to_fae", "fae_to_en"}:
            direction = "en_to_fae"
        if not original:
            message = "Enter a word or short phrase to translate."
        elif len(original) > MAX_TEXT_LENGTH:
            message = f"Keep phrases to {MAX_TEXT_LENGTH} characters or fewer."
        else:
            translation_input = (
                rewrite_english_possessives(original)
                if direction == "en_to_fae" else original
            )
            rules = db.execute(
                "SELECT * FROM language_rules WHERE enabled = 1 AND kind = 'suffix' ORDER BY id"
            ).fetchall()
            suffix_field = "source_suffix" if direction == "en_to_fae" else "target_suffix"
            rules = sorted(rules, key=lambda rule: len(rule[suffix_field]), reverse=True)
            conjugations = db.execute(
                "SELECT * FROM language_rules WHERE enabled = 1 AND kind = 'conjugation'"
            ).fetchall()
            entries = lookup_entries_for_translation(
                db, translation_input, direction, rules, conjugations
            )
            if direction == "en_to_fae":
                entries = cache_english_verb_forms(
                    db, translation_input, entries, conjugations
                )
            result, unknown_words, pronunciation = translate_text(
                translation_input, direction, entries, rules, conjugations
            )
            source, target = ("en", "fae") if direction == "en_to_fae" else ("fae", "en")
            db.execute(
                "INSERT INTO translation_history "
                "(source_language, target_language, original_text, translated_text, "
                "pronunciation_text, unknown_words) VALUES (?, ?, ?, ?, ?, ?)",
                (source, target, original, result, pronunciation, ", ".join(unknown_words)),
            )
            db.commit()

    recent = db.execute(
        "SELECT * FROM translation_history ORDER BY id DESC LIMIT 4"
    ).fetchall()
    return render_template(
        "translate.html",
        result=result,
        pronunciation=pronunciation,
        unknown_words=unknown_words,
        message=message,
        original=original,
        direction=direction,
        recent=recent,
        **page_data(),
    )


@app.route("/dictionary", methods=["GET", "POST"])
def dictionary():
    db = get_db()
    message = None
    if request.method == "POST":
        english = request.form.get("english", "").strip()
        faeric = request.form.get("faeric", "").strip()
        pronunciation = request.form.get("pronunciation", "").strip()
        part_of_speech = request.form.get("part_of_speech", "").strip()
        notes = request.form.get("notes", "").strip()
        if not english or not faeric:
            message = "Enter both the English and Faeric word."
        elif max(map(len, (english, faeric, pronunciation, part_of_speech, notes))) > 120:
            message = "Keep each field to 120 characters or fewer."
        else:
            try:
                db.execute(
                    "INSERT INTO lexicon_entries "
                    "(english, faeric, english_norm, faeric_norm, part_of_speech, notes, pronunciation) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (english, faeric, normalize_english(english), normalize_faeric(faeric), part_of_speech, notes, pronunciation),
                )
                db.execute(
                    "UPDATE app_metadata SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT) "
                    "WHERE key = 'lexicon_entry_count'"
                )
                db.commit()
                return redirect(url_for("dictionary", saved="1"))
            except sqlite3.IntegrityError:
                db.rollback()
                message = "That exact English–Faeric pair is already in the lexicon."

    search = request.args.get("q", "").strip()[:120]
    page = request.args.get("page", default=1, type=int) or 1
    page = max(1, page)
    where = ""
    parameters = []
    if search:
        english_prefix = normalize_english(search)
        faeric_prefix = normalize_faeric(search)
        english_upper = prefix_upper_bound(english_prefix)
        faeric_upper = prefix_upper_bound(faeric_prefix)
        english_clause = "(english_norm >= ? AND english_norm < ?)" if english_upper else "english_norm >= ?"
        faeric_clause = "(faeric_norm >= ? AND faeric_norm < ?)" if faeric_upper else "faeric_norm >= ?"
        where = f"WHERE {english_clause} OR {faeric_clause}"
        parameters.extend((english_prefix, english_upper) if english_upper else (english_prefix,))
        parameters.extend((faeric_prefix, faeric_upper) if faeric_upper else (faeric_prefix,))

    total_entries = db.execute(
        f"SELECT COUNT(*) FROM lexicon_entries {where}", parameters
    ).fetchone()[0]
    page_count = max(1, (total_entries + LEXICON_PAGE_SIZE - 1) // LEXICON_PAGE_SIZE)
    page = min(page, page_count)
    entries = db.execute(
        f"SELECT * FROM lexicon_entries {where} "
        "ORDER BY english_norm, id LIMIT ? OFFSET ?",
        [*parameters, LEXICON_PAGE_SIZE, (page - 1) * LEXICON_PAGE_SIZE],
    ).fetchall()
    if request.args.get("saved"):
        message = "Word added to your lexicon."
    if request.args.get("deleted"):
        message = "Word removed from your lexicon."
    if request.args.get("updated"):
        message = "Dictionary entry updated."
    if request.args.get("import_error"):
        message = request.args.get("import_error", "CSV import failed.")[:200]
    if request.args.get("imported"):
        message = (
            f"Imported {request.args.get('imported')} entries; "
            f"skipped {request.args.get('skipped', '0')} duplicates and "
            f"{request.args.get('invalid', '0')} invalid rows."
        )
    return render_template(
        "dictionary.html", entries=entries, message=message, search=search,
        page=page, page_count=page_count, total_entries=total_entries, **page_data()
    )


@app.route("/dictionary/<int:entry_id>/edit", methods=["GET", "POST"])
def edit_entry(entry_id):
    db = get_db()
    stored_entry = db.execute(
        "SELECT * FROM lexicon_entries WHERE id = ?", (entry_id,)
    ).fetchone()
    if stored_entry is None:
        abort(404)

    entry = dict(stored_entry)
    message = None
    page = request.values.get("page", default=1, type=int) or 1
    page = max(1, page)
    search = request.values.get("q", "").strip()[:120]
    if request.method == "POST":
        for field in ("english", "faeric", "pronunciation", "part_of_speech", "notes"):
            entry[field] = request.form.get(field, "").strip()
        if not entry["english"] or not entry["faeric"]:
            message = "Enter both the English and Faeric word."
        elif max(len(entry[field]) for field in (
            "english", "faeric", "pronunciation", "part_of_speech", "notes"
        )) > 120:
            message = "Keep each field to 120 characters or fewer."
        else:
            try:
                db.execute(
                    "UPDATE lexicon_entries SET english = ?, faeric = ?, english_norm = ?, "
                    "faeric_norm = ?, part_of_speech = ?, notes = ?, pronunciation = ? "
                    "WHERE id = ?",
                    (
                        entry["english"], entry["faeric"],
                        normalize_english(entry["english"]), normalize_faeric(entry["faeric"]),
                        entry["part_of_speech"], entry["notes"], entry["pronunciation"], entry_id,
                    ),
                )
                db.commit()
                return redirect(
                    url_for("dictionary", updated="1", page=page, q=search)
                )
            except sqlite3.IntegrityError:
                db.rollback()
                message = "That exact English–Faeric pair is already in the lexicon."

    return render_template(
        "edit_entry.html", entry=entry, message=message, page=page, search=search,
        **page_data(),
    )


@app.post("/dictionary/import")
def import_dictionary():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return redirect(url_for("dictionary", import_error="Choose a CSV file."))

    text_stream = io.TextIOWrapper(upload.stream, encoding="utf-8-sig", newline="")
    reader = csv.DictReader(text_stream)
    headers = {name.strip().casefold() for name in (reader.fieldnames or []) if name}
    if not {"english", "faeric"}.issubset(headers):
        return redirect(
            url_for("dictionary", import_error="CSV needs English and Faeric columns.")
        )

    db = get_db()
    imported = skipped = invalid = 0
    batch = []
    db.execute("BEGIN")
    try:
        for source_row in reader:
            if any(key is None or not isinstance(value, str) for key, value in source_row.items()):
                invalid += 1
                continue
            row = {
                (key or "").strip().casefold(): (value or "").strip()
                for key, value in source_row.items()
            }
            english = row.get("english", "")
            faeric = row.get("faeric", "")
            pronunciation = row.get("pronunciation", "")
            part_of_speech = row.get("part_of_speech", "")
            notes = row.get("notes", "")
            values = (english, faeric, pronunciation, part_of_speech, notes)
            if not english or not faeric or max(map(len, values)) > 120:
                invalid += 1
                continue
            batch.append(
                (
                    english, faeric, normalize_english(english), normalize_faeric(faeric),
                    part_of_speech, notes, pronunciation,
                )
            )
            if len(batch) >= 1000:
                before = db.total_changes
                db.executemany(
                    """INSERT OR IGNORE INTO lexicon_entries
                       (english, faeric, english_norm, faeric_norm, part_of_speech, notes, pronunciation)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    batch,
                )
                imported += db.total_changes - before
                skipped += len(batch) - (db.total_changes - before)
                batch.clear()

        if batch:
            before = db.total_changes
            db.executemany(
                """INSERT OR IGNORE INTO lexicon_entries
                   (english, faeric, english_norm, faeric_norm, part_of_speech, notes, pronunciation)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                batch,
            )
            imported += db.total_changes - before
            skipped += len(batch) - (db.total_changes - before)
        db.execute(
            "UPDATE app_metadata SET value = "
            "CAST(CAST(value AS INTEGER) + ? AS TEXT) WHERE key = 'lexicon_entry_count'",
            (imported,),
        )
        db.commit()
    except (csv.Error, UnicodeDecodeError):
        db.rollback()
        return redirect(
            url_for("dictionary", import_error="Could not read the CSV. Save it as UTF-8 and try again.")
        )
    finally:
        text_stream.detach()

    return redirect(
        url_for("dictionary", imported=imported, skipped=skipped, invalid=invalid)
    )


@app.post("/dictionary/<int:entry_id>/delete")
def delete_entry(entry_id):
    db = get_db()
    deleted = db.execute("DELETE FROM lexicon_entries WHERE id = ?", (entry_id,)).rowcount
    if deleted:
        db.execute(
            "UPDATE app_metadata SET value = "
            "CAST(MAX(0, CAST(value AS INTEGER) - ?) AS TEXT) "
            "WHERE key = 'lexicon_entry_count'",
            (deleted,),
        )
    db.commit()
    return redirect(
        url_for(
            "dictionary", deleted="1", page=request.form.get("page", 1),
            q=request.form.get("q", "")[:120]
        )
    )


@app.route("/rules", methods=["GET", "POST"])
def rules():
    db = get_db()
    message = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        source_suffix = request.form.get("source_suffix", "").strip()
        target_suffix = request.form.get("target_suffix", "").strip()
        description = request.form.get("description", "").strip()
        if not name or not source_suffix or not target_suffix:
            message = "Enter a name and both suffixes."
        elif max(map(len, (name, source_suffix, target_suffix, description))) > 80:
            message = "Keep each rule field to 80 characters or fewer."
        else:
            db.execute(
                "INSERT INTO language_rules (name, source_suffix, target_suffix, description) "
                "VALUES (?, ?, ?, ?)",
                (name, source_suffix, target_suffix, description),
            )
            db.commit()
            return redirect(url_for("rules", saved="1"))

    all_rules = db.execute(
        "SELECT * FROM language_rules WHERE kind = 'suffix' ORDER BY id DESC"
    ).fetchall()
    conjugations = db.execute(
        "SELECT * FROM language_rules WHERE kind = 'conjugation' ORDER BY "
        "CASE tense WHEN 'present' THEN 1 WHEN 'past' THEN 2 ELSE 3 END"
    ).fetchall()
    if request.args.get("saved"):
        message = "Language rule added."
    if request.args.get("deleted"):
        message = "Rule deleted."
    return render_template(
        "rules.html", rules=all_rules, conjugations=conjugations,
        message=message, **page_data()
    )


@app.post("/rules/<int:rule_id>/delete")
def delete_rule(rule_id):
    db = get_db()
    db.execute("DELETE FROM language_rules WHERE id = ?", (rule_id,))
    db.commit()
    return redirect(url_for("rules", deleted="1"))


@app.route("/history")
def history():
    db = get_db()
    rows = db.execute(
        """SELECT h.*, source.name AS source_name, target.name AS target_name
           FROM translation_history AS h
           JOIN languages AS source ON source.code = h.source_language
           JOIN languages AS target ON target.code = h.target_language
           ORDER BY h.id DESC LIMIT 100"""
    ).fetchall()
    return render_template("history.html", rows=rows, **page_data())


initialize_db()


if __name__ == "__main__":
    app.run(debug=False)
