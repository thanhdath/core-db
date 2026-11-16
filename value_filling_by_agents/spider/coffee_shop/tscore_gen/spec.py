"""Specification loading: value domains, enumerations, ranges, table sizes, NULL targets."""
import json
import os

MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
          'October', 'November', 'December']
YEARS = ['2005', '2006', '2007', '2008', '2009', '2010', '2011', '2012']
ADDRESSES = ['1200 Main Street', '1111 Main Street', '1330 Baltimore Street', '909 Walnut Street',
             '414 E. 12th Street', '1201 Walnut Street', '2345 McGee Street', '909 Main Street',
             'Hartford', 'Waterbury', 'Cheshire', 'Bridgeport']
MEMBER_ADDRESSES = ['Hartford', 'Waterbury', 'Cheshire', 'Bridgeport', 'Harford', 'New Haven',
                    'Stamford', 'Norwalk']
NAMES = ['Ashby, Lazale', 'Breton, Robert', 'Campbell, Jessie', 'Cobb, Sedrick', 'Hayes, Steven',
         'Komisarjevsky, Joshua', 'Peeler, Russell', 'Reynolds, Richard', 'Smith, John', 'Doe, Jane',
         'Brown, Alice', 'Green, Bob', 'White, Carol', 'Black, Dan', 'Gray, Eve', 'Stone, Frank',
         'Wood, Grace', 'Hill, Hank', 'Lake, Iris', 'Park, Jack']


def default_specification() -> dict:
    """Fallback specification (the one shipped with this database)."""
    return {
        'table_sizes': {'shop': 10, 'member': 10, 'happy_hour': 10, 'happy_hour_member': 6},
        'null_targets': ['member.Name', 'member.Membership_card', 'member.Age', 'member.Time_of_purchase',
                         'member.Level_of_membership', 'member.Address', 'shop.Address', 'shop.Num_of_staff',
                         'shop.Score', 'shop.Open_Year', 'happy_hour.Num_of_shaff_in_charge',
                         'happy_hour_member.Total_amount'],
        'domains': {
            'member.Membership_card': {'enum': ['Black', 'White']},
            'member.Age': {'range': [18, 80]},
            'member.Level_of_membership': {'range': [1, 30]},
            'member.Time_of_purchase': {'range': [0, 100]},
            'shop.Score': {'range': [0.0, 50.0], 'real': True},
            'shop.Num_of_staff': {'numeric_text': [1, 500]},
            'shop.Open_Year': {'enum': YEARS},
            'happy_hour.Month': {'enum': MONTHS},
            'happy_hour.Num_of_shaff_in_charge': {'range': [1, 50]},
            'happy_hour_member.Total_amount': {'range': [0.0, 100.0], 'real': True},
        },
        'pools': {
            'member.Address': MEMBER_ADDRESSES,
            'member.Name': NAMES,
            'shop.Address': ADDRESSES,
        },
        'boundaries': {
            'member.Address': ['Waterbury', 'waterbury', 'Harford', 'harford'],
            'member.Age': [29, 30, 31, 39, 40, 41],
            'happy_hour.Month': ['May', 'may'],
            'member.Membership_card': ['Black', 'black'],
        },
        'like_variants': {
            'member.Address': ['%Hartford%', 'Hartford', 'Hartfore', 'Hartford x', 'hartford',
                               '%Harford%', 'Harford', 'Harfore', 'Harford x', 'harford', '%Waterbury%',
                               'Waterbury'],
        },
        'duplicate_share': {'member.Address': [0.2, 0.5], 'shop.Address': [0.2, 0.5]},
        'group_sizes': {'happy_hour.Month': [1, 2, 3], 'happy_hour.Shop_ID': [1, 2, 3]},
        'tie_order': {'happy_hour.Month': {'tie_at_rank': [1], 'direction': 'ASC and DESC'}},
        'aggregate_boundary': {'member.Member_ID': [4, 5, 6], 'happy_hour.Month': [1, 2, 3]},
        'unmatched_join': {'shop.Shop_ID': ['happy_hour.Shop_ID'],
                           'happy_hour.Shop_ID': ['shop.Shop_ID']},
    }


def load_specification(path: str) -> dict:
    """Read specification.json and merge it over the default (missing keys keep defaults)."""
    base = default_specification()
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return base
    for k, v in data.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k].update(v)
        else:
            base[k] = v
    return base


def spec_key(table: str, column: str) -> str:
    """Canonical 'table.Column' key used by the specification."""
    return '%s.%s' % (table, column)
