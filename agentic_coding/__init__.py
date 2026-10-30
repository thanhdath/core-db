"""CoRE-DB construction of one training database, in five steps (``build_db.sh`` runs them in order).

1. ``compaction``: minimal row selection and referenced rows of the gold queries (compact database).
2. ``neighbor_query_generation``: grammar mutations and LLM-written neighbors of every gold (construction pairs).
3. ``value_filling``: Designer, Engineer and Reviewer agents write a generation program; it samples instances.
4. ``separation``: which eligible construction pairs every instance separates.
5. ``selection``: greedy set cover over the instances; the compact database is always a member.
"""
