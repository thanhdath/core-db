"""The generation specification, encoded as data (no rule is ever evaluated with SQL)."""
import json
import os

SPEC = {
    "table_sizes_per_instance": {"club": 6, "club_rank": 6, "player": 15,
                                 "competition": 11, "competition_result": 6},
    "size_jitter": 3,
    "enums": {
        "competition.Competition_type": ["Friendly", "Tournament"],
    },
    "enum_variants": {
        "competition.Competition_type": ["Tournament", "tournament", "Friendly", "friendly",
                                         "Tament", "tament", "name", "NAME", "rn", "RN",
                                         "rnam", "RNAM"],
    },
    "ranges": {
        "club_rank.Gold": [0, 11],
        "club_rank.Silver": [0, 11],
        "club_rank.Bronze": [0, 9],
        "club_rank.Total": [0, 31],
        "player.Apps": [0, 30],
        "player.Tries": [0, 9],
        "player.Points": [0, 188],
        "competition.Year": [1990, 2020],
    },
    "boundaries": {
        "player.Points": [8, 9, 10, 11, 19, 20, 21],
        "club_rank.Total": [9, 10, 11, 12],
    },
    "formats": {
        "club.Start_year": "year",
        "competition_result.Score": "score",
        "player.Goals": "goals",
    },
    "formulas": {
        "club_rank.Total": {"op": "sum", "of": ["club_rank.Gold", "club_rank.Silver",
                                               "club_rank.Bronze"]},
    },
    "non_negative": ["club_rank.Gold", "club_rank.Silver", "club_rank.Bronze",
                     "club_rank.Total", "player.Apps", "player.Tries", "player.Points"],
    "null_targets": ["player.Club_ID", "club_rank.Gold", "club_rank.Silver",
                     "club_rank.Bronze", "club_rank.Total", "player.Position",
                     "player.Goals", "competition.Year", "competition.Competition_type",
                     "competition.Country", "competition_result.Score"],
    "duplicate_share_columns": ["club.name", "competition.Country", "player.name",
                                "player.Position"],
    "group_size_columns": ["player.Player_ID", "competition.Country"],
    "unmatched_join": {
        "parents": ["club.Club_ID", "competition.Competition_ID"],
        "child_null_fk": ["player.Club_ID"],
    },
    "ties_for_order_limit": {"club.Region": {"tie_at_rank": 100, "direction": "ASC"}},
    "rows_with_different_values": ["club_rank.Gold", "club_rank.Silver"],
    "aggregate_boundary": {"competition.Competition_type": [4, 5, 6]},
    "name_pools": {
        "club.name": ["AIB", "BK Slide", "IFG", "ASC", "HGS2", "HSBIF"],
        "player.name": ["Michael Platt", "Dave Halley", "James Evans", "Tame Tupou",
                        "Iestyn Harris", "Paul Deacon (c)", "Joe Vagana", "Terry Newton"],
        "player.Position": ["Full Back", "Right Wing", "Right Centre", "Left Wing",
                            "Stand Off", "Scrum Half", "Prop", "Hooker"],
        "club.Region": ["USA", "UK", "China", "Japan", "England", "Brazil"],
        "competition.Country": ["Italy", "Spain", "Australia", "Russia", "Slovenia",
                                "Ireland"],
    },
}


def load_specification(root: str = None) -> dict:
    """Return the specification; prefer tscore_gen/specification.json if present."""
    if root:
        p = os.path.join(root, 'specification.json')
        if os.path.exists(p):
            try:
                with open(p) as f:
                    return json.load(f)
            except Exception:
                pass
    return SPEC
