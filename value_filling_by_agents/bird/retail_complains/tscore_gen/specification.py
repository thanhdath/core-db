"""The generation specification, encoded as Python data (no SQL is ever evaluated)."""

STATES = ["AL", "AR", "AZ", "CA", "CO", "CT", "DC", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS",
          "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY",
          "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
          "WI", "WY"]
REGIONS = ["South", "West", "Northeast", "Midwest"]
DIVISIONS = ["Middle Atlantic", "South Atlantic", "East North Central", "Pacific", "Mountain",
             "New England", "East South Central", "West South Central", "West North Central"]
SEXES = ["Male", "Female"]
PRIORITIES = [0, 1, 2]
TYPES = ["NW", "PS", "NE", "TT", "IN", "PE"]
OUTCOMES = ["AGENT", "HANG", "PHANTOM"]
SERVERS = ["MICHAL", "TOVA", "YIFAT", "AVNI", "STEREN", "ANAT", "MIKI", "DORIT"]
PRODUCTS_EVENTS = ["Bank account or service", "Credit card"]
SUBPRODUCTS = ["Checking account", "Savings account", "Other bank product/service",
               "(CD) Certificate of deposit", "Cashing a check without an account"]
TAGS = ["Older American", "Older American, Servicemember", "Servicemember"]
CONSENT = ["N/A", "Consent not provided", "Consent provided", "Other"]
SUBMITTED = ["Email", "Fax", "Postal mail", "Referral", "Web", "Phone"]
RESPONSES = ["Closed with explanation", "Closed with relief", "Closed without relief",
             "Closed with non-monetary relief", "In progress", "Closed with monetary relief", "Closed",
             "Untimely response"]
TIMELY = ["Yes", "No"]
DISPUTED = ["No", "Yes"]
STARS = [1, 2, 3, 4, 5]
PRODUCTS_REVIEWS = ["Eagle National Mortgage", "Eagle National Bank", "Eagle Capital"]

EXCEPTIONS = {
    ("state", "StateCode"): {"pattern": "text_enum",
                             "targets": {"values": STATES, "unmatched_join_rows": True}},
    ("state", "State"): {"pattern": "text_free", "targets": {}},
    ("state", "Region"): {"pattern": "text_enum", "targets": {"values": REGIONS}},

    ("district", "district_id"): {"pattern": "integer_range",
                                  "targets": {"min": 1, "max": 77, "unmatched_join_rows": True}},
    ("district", "city"): {"pattern": "text_free",
                           "targets": {"boundary_literals": ["Norwalk", "Indianapolis", "New York City"],
                                       "ties_for_order_limit": [1]}},
    ("district", "state_abbrev"): {"pattern": "text_enum",
                                   "targets": {"values": STATES,
                                               "boundary_literals": ["IN", "MA", "MD"],
                                               "unmatched_join_rows": True}},
    ("district", "division"): {"pattern": "text_enum",
                               "targets": {"values": DIVISIONS, "null_share": 0.15}},

    ("client", "client_id"): {"pattern": "text_identifier",
                              "targets": {"format": "C########", "unmatched_join_rows": True,
                                          "ties_for_order_limit": [1]}},
    ("client", "sex"): {"pattern": "text_enum",
                        "targets": {"values": SEXES, "boundary_literals": ["Male", "Female"],
                                    "null_share": 0.15}},
    ("client", "day"): {"pattern": "integer_range", "targets": {"min": 1, "max": 31}},
    ("client", "month"): {"pattern": "integer_range", "targets": {"min": 1, "max": 12}},
    ("client", "year"): {"pattern": "integer_range", "targets": {"min": 1900, "max": 2017}},
    ("client", "age"): {"pattern": "integer_range",
                        "targets": {"min": 18, "max": 100,
                                    "boundary_literals": [49, 50, 51, 64, 65, 66]}},
    ("client", "social"): {"pattern": "ssn_us", "targets": {}},
    ("client", "first"): {"pattern": "text_name", "targets": {"duplicates_for_distinct": 0.35}},
    ("client", "middle"): {"pattern": "text_name",
                           "targets": {"duplicates_for_distinct": 0.35,
                                       "boundary_literals": ["Bronx", "Eliza", "Lewis"]}},
    ("client", "last"): {"pattern": "text_name",
                         "targets": {"duplicates_for_distinct": 0.35,
                                     "boundary_literals": ["Pierce", "Hicks"]}},
    ("client", "phone"): {"pattern": "phone_us", "targets": {}},
    ("client", "email"): {"pattern": "email",
                          "targets": {"like_near_variant": ["%@gmail.com", "%@outlook.com",
                                                            "@gmail.con", "@GMAIL.COM",
                                                            "@outlook.con", "@OUTLOOK.COM"],
                                      "null_share": 0.15}},
    ("client", "address_1"): {"pattern": "text_free", "targets": {}},
    ("client", "address_2"): {"pattern": "text_free", "targets": {"null_share": 0.985}},
    ("client", "city"): {"pattern": "text_free",
                         "targets": {"boundary_literals": ["Norwalk", "Indianapolis"]}},
    ("client", "state"): {"pattern": "text_enum", "targets": {"values": STATES}},
    ("client", "zipcode"): {"pattern": "zipcode", "targets": {"min": 1000, "max": 99999}},
    ("client", "district_id"): {"pattern": "integer_range",
                                "targets": {"min": 1, "max": 77, "unmatched_join_rows": True}},

    ("callcenterlogs", "Date received"): {"pattern": "date_iso",
                                          "targets": {"min": "2011-01-01", "max": "2017-12-31"}},
    ("callcenterlogs", "Complaint ID"): {"pattern": "text_identifier",
                                         "targets": {"format": "CR#######", "unmatched_join_rows": True}},
    ("callcenterlogs", "rand client"): {"pattern": "text_identifier",
                                        "targets": {"format": "C########", "unmatched_join_rows": True,
                                                    "null_share": 0.374}},
    ("callcenterlogs", "phonefinal"): {"pattern": "phone_us", "targets": {}},
    ("callcenterlogs", "vru+line"): {"pattern": "text_identifier",
                                     "targets": {"format": "AA####", "null_share": 0.246}},
    ("callcenterlogs", "call_id"): {"pattern": "integer_range",
                                    "targets": {"min": 1, "max": 99999, "null_share": 0.246}},
    ("callcenterlogs", "priority"): {"pattern": "integer_enum",
                                     "targets": {"values": PRIORITIES, "null_share": 0.246}},
    ("callcenterlogs", "type"): {"pattern": "text_enum",
                                 "targets": {"values": TYPES, "null_share": 0.246}},
    ("callcenterlogs", "outcome"): {"pattern": "text_enum",
                                    "targets": {"values": OUTCOMES, "null_share": 0.246}},
    ("callcenterlogs", "server"): {"pattern": "text_enum",
                                   "targets": {"values": SERVERS, "null_share": 0.246}},
    ("callcenterlogs", "ser_start"): {"pattern": "time_hhmmss", "targets": {}},
    ("callcenterlogs", "ser_exit"): {"pattern": "time_hhmmss", "targets": {}},
    ("callcenterlogs", "ser_time"): {"pattern": "time_hhmmss", "targets": {}},

    ("events", "Date received"): {"pattern": "date_iso",
                                  "targets": {"min": "2011-01-01", "max": "2017-12-31"}},
    ("events", "Product"): {"pattern": "text_enum", "targets": {"values": PRODUCTS_EVENTS}},
    ("events", "Sub-product"): {"pattern": "text_enum",
                                "targets": {"values": SUBPRODUCTS, "null_share": 0.40}},
    ("events", "Issue"): {"pattern": "text_free", "targets": {}},
    ("events", "Sub-issue"): {"pattern": "text_free", "targets": {"null_share": 1.0}},
    ("events", "Consumer complaint narrative"): {"pattern": "text_free",
                                                 "targets": {"null_share": 0.81}},
    ("events", "Tags"): {"pattern": "text_enum", "targets": {"values": TAGS, "null_share": 0.86}},
    ("events", "Consumer consent provided?"): {"pattern": "text_enum",
                                               "targets": {"values": CONSENT}},
    ("events", "Submitted via"): {"pattern": "text_enum", "targets": {"values": SUBMITTED}},
    ("events", "Date sent to company"): {"pattern": "date_iso",
                                         "targets": {"min": "2011-01-01", "max": "2017-12-31"}},
    ("events", "Company response to consumer"): {"pattern": "text_enum",
                                                 "targets": {"values": RESPONSES}},
    ("events", "Timely response?"): {"pattern": "text_enum", "targets": {"values": TIMELY}},
    ("events", "Consumer disputed?"): {"pattern": "text_enum",
                                       "targets": {"values": DISPUTED, "null_share": 0.04}},
    ("events", "Complaint ID"): {"pattern": "text_identifier",
                                 "targets": {"format": "CR#######", "unmatched_join_rows": True}},
    ("events", "Client_ID"): {"pattern": "text_identifier",
                              "targets": {"format": "C########", "unmatched_join_rows": True,
                                          "boundary_literals": ["C00007127"]}},

    ("reviews", "Date"): {"pattern": "date_iso",
                          "targets": {"min": "2013-01-01", "max": "2018-12-31"}},
    ("reviews", "Stars"): {"pattern": "integer_enum",
                           "targets": {"values": STARS,
                                       "boundary_literals": [0, 1, 2, 4, 5, 6],
                                       "null_share": 0.15}},
    ("reviews", "Reviews"): {"pattern": "text_free", "targets": {"null_share": 0.88}},
    ("reviews", "Product"): {"pattern": "text_enum",
                             "targets": {"values": PRODUCTS_REVIEWS,
                                         "duplicates_for_distinct": 0.35}},
    ("reviews", "district_id"): {"pattern": "integer_range",
                                 "targets": {"min": 1, "max": 77, "unmatched_join_rows": True}},
}

DEPENDENCIES = [
    ("district", "state_abbrev", "state", "StateCode"),
    ("client", "district_id", "district", "district_id"),
    ("callcenterlogs", "rand client", "client", "client_id"),
    ("events", "Complaint ID", "callcenterlogs", "Complaint ID"),
    ("events", "Client_ID", "client", "client_id"),
    ("reviews", "district_id", "district", "district_id"),
]

TABLE_SIZES = {"state": 48, "district": 77, "client": 230, "callcenterlogs": 230,
               "events": 230, "reviews": 230}
