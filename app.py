"""A small local English/Faeric translator backed by SQLite."""

import re
import sqlite3
import unicodedata
from pathlib import Path

from flask import Flask, g, redirect, render_template, request, url_for


ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "instance" / "faeric.sqlite3"
TOKEN_RE = re.compile(r"\w+|[^\w\s]+|\s+", re.UNICODE)
MAX_TEXT_LENGTH = 500

# Transcribed from sources/Fae Rune Pronunciation Guide and Dictionary.docx.
# The Faeric spellings are the document's Latin-keyboard rune transcriptions.
SOURCE_LEXICON = [
    ("light", "t", "rune meaning", "t", "Rune name: Trye; also life and joy"),
    ("life", "t", "rune meaning", "t", "Rune name: Trye; also light and joy"),
    ("joy", "t", "rune meaning", "t", "Rune name: Trye; also light and life"),
    ("sun", "d", "rune meaning", "d", "Rune name: Drye"),
    ("heat", "f", "rune meaning", "f", "Rune name: Frey"),
    ("fire", "v", "rune meaning", "v", "Rune name: Vey"),
    ("air", "i", "rune meaning", "e͡ɪ", "Rune name: Ave"),
    ("cloud", "e", "rune meaning", "iː", "Rune name: Eve"),
    ("water", "w", "rune meaning", "w", "Rune name: Uan"),
    ("rain", "W", "rune meaning", "", ""),
    ("earth", "R", "rune meaning", "ɹ", "Rune name: T’r"),
    ("stone", "R", "rune meaning", "", ""),
    ("lava", "A", "rune meaning", "a͡ɪ", "Rune name: Aine"),
    ("lightning", "L", "rune meaning", "l", "Rune name: L’v"),
    ("cold", "s", "rune meaning", "s", "Rune name: Syle"),
    ("ice", "Z", "rune meaning", "z", "Rune name: Zyle"),
    ("plant", "p", "rune meaning", "p", "Rune name: Pl’v"),
    ("wood", "B", "rune meaning", "b", "Rune name: Bl’v"),
    ("dark", "k", "rune meaning", "k", "Rune name: Kor; also death and misery"),
    ("death", "k", "rune meaning", "k", "Rune name: Kor; also dark and misery"),
    ("misery", "k", "rune meaning", "k", "Rune name: Kor; also dark and death"),
    ("moon", "K", "rune meaning", "", ""),
    ("yet", "G", "rune meaning", "g", "Rune name: Gyur"),
    ("and", "H", "rune meaning", "h", "Rune name: Yhol"),
    ("to", "j", "rune meaning", "d͡ʒ", "Rune name: Jhu"),
    ("from", "J", "rune meaning", "", "Rune name: Jhu; meaning from/of"),
    ("of", "J", "rune meaning", "", "Rune name: Jhu; meaning from/of"),
    ("or", "n", "rune meaning", "n", "Rune name: Nur"),
    ("nor", "m", "rune meaning", "m", "Rune name: Mur"),
    ("so", "u", "rune meaning", "u", "Rune name: Urd"),
    ("but", "O", "rune meaning", "o͡ʊ", "Rune name: Ord"),
    ("for", "y", "rune meaning", "j", "Rune name: Yere"),
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

app = Flask(__name__)
app.config["DATABASE"] = DATABASE


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


def initialize_db():
    db = connect_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS languages (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL
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
    for entry in db.execute("SELECT id, english, faeric FROM lexicon_entries").fetchall():
        db.execute(
            "UPDATE lexicon_entries SET english_norm = ?, faeric_norm = ? WHERE id = ?",
            (normalize_english(entry["english"]), normalize_faeric(entry["faeric"]), entry["id"]),
        )
    # Update the original source entry in databases initialized before the user
    # changed the Faeric form for "no" from ni / Nai to Mai.
    db.execute(
        """UPDATE lexicon_entries
           SET faeric = 'Mai', faeric_norm = 'Mai', pronunciation = 'Mai', notes = ''
           WHERE english_norm = 'no' AND faeric_norm = 'ni'
             AND part_of_speech = 'answer'"""
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_lexicon_pair "
        "ON lexicon_entries(english_norm, faeric_norm)"
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
    db.commit()
    db.close()


def english_verb_form(lemma, tense):
    if tense == "past":
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


def preferred_pronoun(rows, direction):
    target_field = "faeric" if direction == "en_to_fae" else "english"
    candidates = [row for row in rows if row["part_of_speech"] == "pronoun"]
    if not candidates:
        return rows[0][target_field]
    # "you" has several politeness and number variants. Use the documented
    # neutral singular form as the default when translating from English.
    if direction == "en_to_fae":
        neutral = [row for row in candidates if "singular, neutral" in row["notes"].casefold()]
        if neutral:
            return neutral[0][target_field]
    return candidates[0][target_field]


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
    unknown = []

    if forward:
        # Apply the source document's pronoun + verb conjugation to simple
        # English subject/verb phrases. English past and "will" are recognized.
        raw_pieces = TOKEN_RE.findall(text)
        index = 0
        generated_forms = set()
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
                            faeric_pronoun = preferred_pronoun(pronouns, direction)
                            form = (
                                conjugation["prefix"]
                                + faeric_pronoun
                                + verb["faeric"]
                                + conjugation["suffix"]
                            )
                            translated.append(form)
                            generated_forms.add(normalize_faeric(form))
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
        for index, piece in enumerate(raw_pieces):
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
                            conjugated_forms[index] = pronoun["english"] + " " + english_verb
                            break
                    if index in conjugated_forms:
                        break
                if index in conjugated_forms:
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
            continue

        normalized = normalize_english(piece) if forward else normalize_faeric(piece)
        if forward and normalized in conjugated_forms:
            translated.append(piece)
            continue
        if not forward and piece_index in conjugated_forms:
            translated.append(conjugated_forms[piece_index])
            continue
        candidates = words.get(normalized, [])
        result = None
        if candidates:
            if forward:
                result = preferred_pronoun(candidates, direction)
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
                        stem_translation = preferred_pronoun(stem_rows, direction)
                        result = stem_translation + out_suffix
                        break
        if result is None:
            translated.append(piece)
            unknown.append(piece)
        else:
            translated.append(result)

    return "".join(translated), list(dict.fromkeys(unknown))


def page_data():
    db = get_db()
    return {
        "entry_count": db.execute("SELECT COUNT(*) FROM lexicon_entries").fetchone()[0],
        "rule_count": db.execute(
            "SELECT COUNT(*) FROM language_rules WHERE enabled = 1"
        ).fetchone()[0],
    }


@app.route("/", methods=["GET", "POST"])
def translate():
    db = get_db()
    result = None
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
            entries = db.execute("SELECT * FROM lexicon_entries").fetchall()
            rules = db.execute(
                "SELECT * FROM language_rules WHERE enabled = 1 AND kind = 'suffix' ORDER BY id"
            ).fetchall()
            suffix_field = "source_suffix" if direction == "en_to_fae" else "target_suffix"
            rules = sorted(rules, key=lambda rule: len(rule[suffix_field]), reverse=True)
            conjugations = db.execute(
                "SELECT * FROM language_rules WHERE enabled = 1 AND kind = 'conjugation'"
            ).fetchall()
            result, unknown_words = translate_text(
                original, direction, entries, rules, conjugations
            )
            source, target = ("en", "fae") if direction == "en_to_fae" else ("fae", "en")
            db.execute(
                "INSERT INTO translation_history "
                "(source_language, target_language, original_text, translated_text, unknown_words) "
                "VALUES (?, ?, ?, ?, ?)",
                (source, target, original, result, ", ".join(unknown_words)),
            )
            db.commit()

    recent = db.execute(
        "SELECT * FROM translation_history ORDER BY id DESC LIMIT 4"
    ).fetchall()
    return render_template(
        "translate.html",
        result=result,
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
                db.commit()
                return redirect(url_for("dictionary", saved="1"))
            except sqlite3.IntegrityError:
                message = "That exact English–Faeric pair is already in the lexicon."

    entries = db.execute(
        "SELECT * FROM lexicon_entries ORDER BY english_norm"
    ).fetchall()
    if request.args.get("saved"):
        message = "Word added to your lexicon."
    if request.args.get("deleted"):
        message = "Word removed from your lexicon."
    return render_template("dictionary.html", entries=entries, message=message, **page_data())


@app.post("/dictionary/<int:entry_id>/delete")
def delete_entry(entry_id):
    db = get_db()
    db.execute("DELETE FROM lexicon_entries WHERE id = ?", (entry_id,))
    db.commit()
    return redirect(url_for("dictionary", deleted="1"))


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
