"""Loads tscore_gen/specification.json if present; otherwise uses built-in defaults for this DB."""
import json
import os

_DEFAULTS = {
    "table_sizes_per_instance": {"country": 20, "city": 40, "address": 60, "language": 6, "category": 16,
                                 "actor": 40, "film": 80, "film_text": 80, "film_actor": 120, "film_category": 80,
                                 "store": 2, "staff": 2, "customer": 60, "inventory": 100, "rental": 120,
                                 "payment": 120},
    "null_targets": ["address.address2", "address.postal_code", "customer.email", "film.description",
                     "film.release_year", "film.original_language_id", "film.length", "film.rating",
                     "film.special_features", "payment.rental_id", "rental.return_date", "staff.picture",
                     "staff.email", "staff.password", "film_text.description"],
    "enums": {"film.rental_rate": [0.99, 2.99, 4.99], "film.rental_duration": [3, 4, 5, 6, 7],
              "film.rating": ["G", "PG", "PG-13", "R", "NC-17"],
              "customer.active": [0, 1], "staff.active": [0, 1],
              "customer.store_id": [1, 2], "staff.store_id": [1, 2], "store.store_id": [1, 2]},
    "ranges": {"film.rental_duration": [3, 7], "film.replacement_cost": [9.99, 29.99],
               "film.length": [46, 185], "payment.amount": [0.0, 999.99]},
    "comparison_boundary": {
        "film.film_id": [0, 1, 2, 995, 996, 997],
        "customer.customer_id": [14, 15, 16, 99, 100, 101],
        "customer.first_name": ["RUTH", "ruth", "Maria", "maria", "MARY", "mary"],
        "customer.last_name": ["ELLA", "ella", "MARTINEZ", "martinez", "SMITH", "smith"],
        "actor.first_name": ["Dan", "dan", "Nina", "nina", "Kilmer", "kilmer"],
        "actor.last_name": ["Kilmer", "kilmer", "Jovovich", "jovovich", "Soto", "soto"],
        "category.name": ["Horror", "horror", "Children", "children", "Documentary", "documentary"],
        "film.title": ["Blanket Beverly", "blanket beverly", "ACADEMY DINOSAUR", "academy dinosaur",
                       "Blan Beverly", "blan beverly"],
        "film.rental_rate": [2.99, 4.99],
        "film.rental_duration": [4, 5, 6, 7],
        "film.length": [99, 100, 101, 112, 113, 114],
        "film.rating": ["PG-13", "NC-17"],
        "city.city": ["Lethbridge", "lethbridge", "Abu Dhabi", "abu dhabi", "Lethbidge", "lethbidge"],
        "rental.rental_date": ["2005-05-26 00:00:00.0", "2005-05-27 00:00:00.0", "2005-05-28 00:00:00.0",
                               "2005-05-31 00:00:00.0", "2005-06-01 00:00:00.0", "2005-06-02 00:00:00.0"],
        "payment.payment_date": ["2005-01-01 00:00:00.0", "2005-05-30 03:43:54.0", "2005-05-30 03:43:55.0",
                                 "2005-12-31 00:00:00.0", "2006-01-01 00:00:00.0"],
        "rental.rental_id": [0, 1, 2, 9, 10, 11],
        "payment.rental_id": [0, 1, 2, 9, 10, 11],
        "store.store_id": [1, 2],
        "staff.store_id": [1, 2],
        "customer.store_id": [1, 2],
        "customer.active": [0, 1],
        "film_actor.film_id": [112, 113, 114],
        "category.category_id": [10, 11, 12],
        "film_category.category_id": [10, 11, 12],
        "address.address_id": [1, 2, 3],
        "film_text.film_id": [995, 996, 997],
    },
    "like_variants": {
        "film.special_features": ["deleted scenes", "%deleted scenes%", "%Deleted Scenes%",
                                  "deleted scenet", "deleted scenes x", "DELETED SCENES", "Deleted Scenes",
                                  "Deleted Scenet", "Deleted Scenes x"],
        "payment.payment_date": ["2005-06%", "2005-06-01", "2005-08%", "2005-06-%", "2005-08", "2005-08-01",
                                 "2005-05-31 00:00:00.0", "2005-06-01 00:00:00.0", "2005-06-30 00:00:00.0",
                                 "2005-07-01 00:00:00.0", "2005-07-31 00:00:00.0", "2005-08-01 00:00:00.0",
                                 "2005-08-31 00:00:00.0", "2005-09-01 00:00:00.0"],
    },
    "not_in": {}}


def load_specificateion():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, 'specification.json')
    if os.path.exists(path):
        try:
            with open(path) as f:
                d = json.load(f)
            return d
        except Exception:
            pass
    return _DEFAULTS
