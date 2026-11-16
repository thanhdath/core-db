"""Specification (tscore_gen/specification.json) as a plain dict, plus the built-in default."""

DEFAULT = {
    "table_sizes": {"works": 43, "chapters": 200, "characters": 200, "paragraphs": 500},
    "size_jitter": 0.25,
    "ranges": {
        "works.Date": [1500, 1650],
        "chapters.Act": [0, 6],
        "chapters.Scene": [1, 8],
        "paragraphs.ParagraphNum": [1, 60],
    },
    "enums": {
        "works.GenreType": ["Comedy", "Tragedy", "History", "Poem", "Sonnet"],
    },
    "boundaries": {
        "works.id": [6, 7, 8, 9, 10],
        "chapters.work_id": [6, 7, 8, 9, 10],
        "chapters.id": [18880, 18881, 18882],
        "chapters.Scene": [1, 2, 3, 4, 5, 6],
        "chapters.Act": [0, 1, 2, 4, 5, 6],
        "characters.id": [1237, 1238, 1239],
        "paragraphs.chapter_id": [18708, 18709, 18710, 18880, 18881, 18882],
        "works.Date": [1592, 1593, 1594, 1598, 1599, 1600],
        "works.Title": ["Twelfth Night", "twelfth night", "Comedy of Errors", "comedy of errors",
                        "Venus and Adonis", "venus and adonis"],
        "works.GenreType": ["Tragedy", "tragedy", "Comedy", "comedy", "History", "history"],
        "characters.CharName": ["antonio", "ANTONIO", "Sir Toby Belch", "sir toby belch",
                                "(stage directions)", "(STAGE DIRECTIONS)"],
        "characters.Abbrev": ["Aedile", "aedile"],
        "chapters.Description": ["Florence. Without the walls. A tucket afar off.",
                                 "florence. without the walls. a tucket afar off."],
        "paragraphs.PlainText": ["His name, I pray you.", "his name, i pray you."],
    },
    "boundary_share": 0.15,
    "duplicate_share": {
        "works.id": 0.30, "characters.CharName": 0.30,
        "works.LongTitle": 0.30, "characters.Description": 0.30,
    },
    "tie_columns": {
        "chapters.Scene": True, "chapters.id": True, "characters.CharName": True,
        "works.Date": True, "paragraphs.ParagraphNum": True,
    },
    "tie_share": 0.20,
    "like_near_variants": {
        "works.Title": "Henry", "works.LongTitle": "Henry",
        "characters.Description": "cousin to the king",
    },
    "aggregate_boundary": {"paragraphs.id": 5},
    "unmatched_parents": {
        "works.id": 0.10, "chapters.id": 0.10, "characters.id": 0.10,
    },
    "text_pools": {
        "works.Title": ["Twelfth Night", "All's Well That Ends Well", "Antony and Cleopatra",
                        "As You Like It", "Comedy of Errors", "Coriolanus", "Cymbeline", "Hamlet",
                        "Henry V", "King Henry IV", "Venus and Adonis", "The Rape of Lucrece"],
        "works.LongTitle": ["Twelfth Night, Or What You Will", "All's Well That Ends Well",
                            "Antony and Cleopatra", "As You Like It", "The Comedy of Errors",
                            "Coriolanus", "Cymbeline, King of Britain",
                            "Tragedy of Hamlet, Prince of Denmark, The",
                            "Life of King Henry the Fifth", "Venus and Adonis"],
        "characters.CharName": ["Antonio", "Sir Toby Belch", "Olivia", "Orsino", "Viola", "Sebastian",
                                "Malvolio", "Feste", "Curio", "Valentine", "Gratiano", "Aedile",
                                "(stage directions)", "First Citizen", "First Officer"],
        "characters.Abbrev": ["Ant.", "Sir To.", "Oli.", "Ors.", "Vio.", "Seb.", "Mal.", "Fes.",
                              "Cur.", "Val.", "Gra.", "Aedile", "Cit.", "Off."],
        "characters.Description": ["", "A senator of Venice", "a Moor, beloved by Tamora",
                                   "an executioner", "Servant to Montague", "a Greek prince",
                                   "servant to Oliver", "wife to Antipholus of Ephesus",
                                   "cousin to the king", "a lord of Syracuse"],
        "chapters.Description": ["DUKE ORSINO's palace.", "The sea-coast.", "OLIVIA'S house.",
                                 "A street.", "OLIVIA's garden.", "Before OLIVIA's house.",
                                 "Rousillon. The COUNT's palace.",
                                 "Florence. Without the walls. A tucket afar off.",
                                 "Rome. A public place.", "Alexandria. A room in the palace."],
        "paragraphs.PlainText": ["[Enter DUKE ORSINO, CURIO, and other Lords; Musicians attending]",
                                 "If music be the food of love, play on;",
                                 "Will you go hunt, my lord?", "What, Curio?", "The hart.",
                                 "His name, I pray you.", "So please my lord, I might not be admitted;",
                                 "O, she that hath a heart of that fine frame"],
    },
    "text_lengths": {"short": [3, 24], "long": [20, 120]},
    "dependencies": [
        {"child_column": "chapters.work_id", "parent_table": "works", "parent_column": "id"},
        {"child_column": "paragraphs.chapter_id", "parent_table": "chapters", "parent_column": "id"},
        {"child_column": "paragraphs.character_id", "parent_table": "characters", "parent_column": "id"},
    ],
    "formulas": {
        "works.id": "id > 0", "chapters.id": "id > 0", "characters.id": "id > 0",
        "paragraphs.id": "id > 0", "chapters.work_id": "work_id > 0",
        "paragraphs.chapter_id": "chapter_id > 0", "paragraphs.character_id": "character_id > 0",
        "paragraphs.ParagraphNum": "ParagraphNum > 0",
    },
    "null_targets": [],
}


def load_specification(raw: dict) -> dict:
    """Merge a pipeline-written specification over the default (missing keys keep defaults)."""
    out = {k: (v.copy() if isinstance(v, dict) else v) for k, v in DEFAULT.items()}
    for k, v in (raw or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def default_specification() -> dict:
    """Deep-ish copy of the built-in default."""
    return load_specification({})
