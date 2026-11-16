"""Specification loader: value domains, enumerations, ranges, NULL shares, dependencies."""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_SPEC_PATH = os.path.join(_HERE, 'specification.json')

_DEFAULT = {
    "table_sizes": {"playstore": 200, "user_reviews": 400},
    "null_share": {
        "playstore.Rating": 0.136, "playstore.Reviews": 0.10,
        "user_reviews.App": 0.10, "user_reviews.Sentiment": 0.10,
        "user_reviews.Sentiment_Polarity": 0.10, "user_reviews.Sentiment_Subjectivity": 0.10,
    },
    "enums": {
        "playstore.Type": ["Free", "Paid", "NaN"],
        "playstore.Content Rating": ["Everyone", "Teen", "Everyone 10+", "Mature 17+",
                                     "Adults only 18+", "Unrated"],
        "user_reviews.Sentiment": ["Positive", "Negative", "Neutral", "nan"],
    },
    "ranges": {
        "playstore.Rating": [1.0, 5.0],
        "playstore.Reviews": [0, 1000000],
        "user_reviews.Sentiment_Polarity": [-1.0, 1.0],
        "user_reviews.Sentiment_Subjectivity": [0.0, 1.0],
    },
    "boundaries": {
        "playstore.Rating": [4.4, 4.5, 4.6, 4.7, 4.8],
        "user_reviews.Sentiment_Polarity": [0.49, 0.5, 0.51, -0.51, -0.5, -0.49],
    },
    "nan_columns": ["user_reviews.Sentiment_Polarity", "user_reviews.Sentiment_Subjectivity"],
    "app_boundary": ["Dino War: Rise of Beasts", "dino war: rise of beasts", "Dragon Ball Legends",
                     "dragon ball legends", "HTC Weather", "htc weather",
                     "10 Best Foods for You", "10 best foods for you"],
    "genres_boundary": ["Dating", "dating", "Role Playing", "role playing", "Weather", "weather",
                        "Photography", "photography"],
    "genres_like": ["role playinh", "role playing x", "ROLE PLAYING", "Weathes", "Weather x"],
    "installs_boundary": ["100,000,000+", "100,000,000", "100,000,001", "100,000,000 x",
                          "100,000,001+", "x 100,000,000+", "5,000+"],
    "category_boundary": ["WEATHER", "weather"],
    "type_boundary": ["Free", "free", "Paid", "paid"],
    "translated_review_boundary": ["nan", "NAN"],
    "size_boundary": ["Dragon Ball Legends", "dragon ball legends"],
    "dependencies": [{"child_column": "user_reviews.App", "parent_table": "playstore",
                      "parent_column": "App"}],
    "fk_null_share": 0.10,
    "fk_copy_share": 0.90,
}


def load_specification(path: str = None) -> dict:
    """Load specification.json (or the built-in fallback) and normalise it."""
    p = path or _SPEC_PATH
    spec = dict(_DEFAULT)
    if os.path.exists(p):
        try:
            with open(p) as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                spec.update(loaded)
        except Exception:
            pass
    return spec
