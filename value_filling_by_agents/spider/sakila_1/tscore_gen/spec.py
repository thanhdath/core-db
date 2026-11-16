"""Specification loading: value domains, ranges, enums, NULL shares, dependencies."""
import json

_EVIDENCE = {
    'table_sizes': {'country': 109, 'city': 200, 'address': 200, 'language': 6, 'category': 16,
                    'actor': 200, 'film': 230, 'film_actor': 230, 'film_category': 230,
                    'film_text': 230, 'store': 2, 'staff': 2, 'customer': 230,
                    'inventory': 230, 'rental': 230, 'payment': 230},
    'constants': {'film.release_year': 2006},
    'ranges': {'film.rental_duration': [3, 4, 5, 6, 7],
               'film.replacement_cost': [12.99, 15.99, 17.99, 18.99, 20.99, 22.99, 26.99, 28.99],
               'film.length': [48, 50, 54, 62, 86, 117, 130, 169]},
    'enums': {'film.rating': ['G', 'PG', 'PG-13', 'R', 'NC-17'],
              'film.special_features': ['Trailers', 'Commentaries', 'Deleted Scenes', 'Behind the Scenes']},
    'boundaries': {'payment.amount': [9.99, 10.0, 10.01],
                   'film.rental_rate': [0.98, 0.99, 1.0],
                   'staff.first_name': ['Elsa', 'elsa']},
    'null_shares': {'address.address2': 0.007, 'address.postal_code': 0.01,
                    'film.original_language_id': 0.99, 'film.description': 0.01,
                    'film.length': 0.01, 'film.special_features': 0.01,
                    'customer.email': 0.01, 'customer.last_update': 0.01,
                    'payment.rental_id': 0.01, 'payment.last_update': 0.01,
                    'rental.return_date': 0.011,
                    'staff.picture': 0.01, 'staff.email': 0.01, 'staff.password': 0.01},
    'duplicate_shares': {'film.language_id': 0.35, 'payment.payment_date': 0.35,
                         'customer.first_name': 0.35},
    'group_sizes': ['actor.first_name', 'actor.last_name', 'film.title', 'film.description',
                    'address.city_id', 'film_category.category_id'],
    'aggregate_boundaries': {'film.film_id': [2, 3, 4, 29, 30, 31],
                             'city.city_id': [2, 3, 4],
                             'country.country_id': [2, 3, 4],
                             'inventory.inventory_id': [2, 3, 4]},
    'unmatched_join': ['actor.actor_id', 'film_actor.actor_id', 'payment.staff_id',
                       'staff.staff_id', 'inventory.film_id'],
    'ties_for_order_limit': {'film.film_id': {'tie_at_rank': [1], 'direction': 'DESC',
                                              'tie_on': ['COUNT(*)']}},
    'comparison_boundaries': {'customer.customer_id': {'equal_and_one_step_from': ['rental.customer_id']}},
    'datetime_columns': ['customer.create_date', 'payment.payment_date', 'rental.rental_date'],
    'datetime_domains': {'customer.create_date': ['2006-02-14 22:04:36', '2006-02-14 22:04:37']},
    'boolean_columns': ['customer.active', 'staff.active'],
    'copy_columns': {'film_text': {'film_id': 'film.film_id', 'title': 'film.title',
                                   'description': 'film.description'}},
}


def spec_from_evidence() -> dict:
    """Return the built-in specification dict."""
    return json.loads(json.dumps(_EVIDENCE))


def load_specification(path: str) -> dict:
    """Load specification.json; missing keys fall back to the built-in evidence."""
    with open(path) as f:
        raw = json.load(f)
    base = spec_from_evidence()
    if isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                base[k].update(v)
            else:
                base[k] = v
    return base


def col_key(table: str, column: str) -> str:
    """'table.column' key used by the specification."""
    return '%s.%s' % (table, column)
