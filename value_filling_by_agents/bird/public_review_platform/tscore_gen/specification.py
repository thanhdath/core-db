"""The generation specification, encoded as data (no SQL is ever evaluated)."""

TABLE_SIZES = {
    'Attributes': 80, 'Categories': 200, 'Compliments': 11, 'Days': 7, 'Years': 10,
    'Business': 400, 'Users': 400, 'Business_Attributes': 800, 'Business_Categories': 800,
    'Business_Hours': 800, 'Checkins': 800, 'Elite': 400, 'Reviews': 800, 'Tips': 800,
    'Users_Compliments': 800,
}

ENUMS = {
    ('Business', 'active'): ['true', 'false', 'True', 'False', 'TRUE', 'FALSE'],
    ('Business', 'review_count'): ['Low', 'Medium', 'High', 'Uber'],
    ('Business', 'state'): ['AZ', 'SC', 'CA', 'Arizona', 'arizona'],
    ('Reviews', 'review_length'): ['Short', 'Medium', 'Long'],
    ('Tips', 'tip_length'): ['Short', 'Medium', 'Long'],
    ('Users', 'user_fans'): ['None', 'Low', 'Medium', 'High', 'Uber'],
    ('Users', 'user_votes_funny'): ['None', 'Low', 'Medium', 'High', 'Uber'],
    ('Users', 'user_votes_useful'): ['None', 'Low', 'Medium', 'High', 'Uber'],
    ('Users', 'user_votes_cool'): ['None', 'Low', 'Medium', 'High', 'Uber'],
    ('Users', 'user_review_count'): ['Low', 'Medium', 'High', 'Uber'],
    ('Users_Compliments', 'number_of_compliments'): ['Low', 'Medium', 'High', 'Uber'],
    ('Compliments', 'compliment_type'): ['photos', 'cool', 'hot', 'note', 'more', 'funny', 'writer',
                                         'plain', 'cute', 'profile', 'list'],
    ('Days', 'day_of_week'): ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'],
    ('Reviews', 'review_votes_funny'): ['None', 'Low', 'Medium', 'High', 'Uber'],
    ('Reviews', 'review_votes_useful'): ['None', 'Low', 'Medium', 'High', 'Uber'],
    ('Reviews', 'review_votes_cool'): ['None', 'Low', 'Medium', 'High', 'Uber'],
}

CHECKIN_LABELS = ['None', 'Low', 'Medium', 'High', 'Uber']
CHECKIN_LABELS_SMALL = ['None', 'Low', 'Medium', 'High']

RANGES = {
    ('Business', 'stars'): (1.0, 5.0, 0.5),
    ('Reviews', 'review_stars'): (1, 5, 1),
    ('Tips', 'likes'): (0, 10, 1),
    ('Users', 'user_yelping_since_year'): (2005, 2014, 1),
    ('Years', 'actual_year'): (2005, 2014, 1),
    ('Years', 'year_id'): (2005, 2014, 1),
}

TIMES = ['12AM', '1AM', '2AM', '3AM', '4AM', '5AM', '6AM', '7AM', '8AM', '9AM', '10AM', '11AM',
         '12PM', '1PM', '2PM', '3PM', '4PM', '5PM', '6PM', '7PM', '8PM', '9PM', '10PM', '11PM']

BOUNDARY = {
    ('Business', 'business_id'): [11, 12, 13, 10681, 10682, 10683],
    ('Business', 'city'): ['Scottsdale', 'scottsdale', 'Sun City Anthem', 'sun city anthem',
                           'Glendale', 'glendale', 'Mesa', 'mesa'],
    ('Business', 'state'): ['AZ', 'az', 'Arizona', 'arizona'],
    ('Business', 'active'): ['true', 'TRUE', 'false', 'FALSE'],
    ('Business', 'stars'): [2.9, 3.0, 3.1, 4.9, 5.0, 5.1],
    ('Categories', 'category_name'): ["Pets", "pets", "Women's Clothing", "women's clothing",
                                      "Men's Clothing", "men's clothing", "Stadiums & Arenas",
                                      "stadiums & arenas"],
    ('Users', 'user_id'): [2, 3, 4, 60775, 60776, 60777],
    ('Users', 'user_fans'): ['High', 'high', 'None', 'none', 'Uber', 'uber'],
    ('Users', 'user_yelping_since_year'): [2008, 2009, 2010, 2011, 2012, 2013],
    ('Business_Attributes', 'attribute_value'): ['false', 'FALSE', 'no', 'NO', 'none', 'NONE',
                                                 'waiter service', 'WAITER SERVICE'],
    ('Business_Attributes', 'business_id'): [1, 2, 3, 1140, 1141, 1142],
    ('Business_Attributes', 'attribute_id'): [0, 1, 2, 3],
    ('Attributes', 'attribute_name'): ['Accepts Credit Cards', 'accepts credit cards', 'Alcohol',
                                       'alcohol', 'Accepts Insurance', 'accepts insurance'],
    ('Reviews', 'review_stars'): [4, 5, 6],
}

NEAR = {
    ('Business', 'city'): ['Phoenix', 'Scottsdale', 'Anthem', 'Tolleson', 'Tempe', 'Yuma'],
    ('Business', 'state'): ['AZ', 'AZ%', '%AZ', '%AZ%'],
    ('Business', 'active'): ['True', 'TRUE', 'False', 'true', '%True'],
    ('Business', 'review_count'): ['Low', 'High', 'Medium', '%Low', '%Low%'],
    ('Categories', 'category_name'): ['Automotive', 'Fashion', 'Food', 'Bars', 'Shopping', 'Accessories'],
    ('Users', 'user_fans'): ['None', 'High', 'Uber', 'Low', '%None', 'None%'],
    ('Business_Attributes', 'attribute_value'): ['none', 'TRUE', '%none%', 'beer_and_wine', 'UE'],
    ('Attributes', 'attribute_name'): ['Alcohol', 'Open 24 Hours', 'waiter_service', 'Good for Kids',
                                       'Caters', 'Wi-Fi'],
    ('Reviews', 'review_length'): ['Long', 'Medium', 'long', 'Medium%', '%long%', 'lng'],
    ('Compliments', 'compliment_type'): ['cute', 'cool'],
    ('Days', 'day_of_week'): ['Sunday', 'Saturday'],
    ('Business_Hours', 'opening_time'): ['9AM', '10AM'],
    ('Business_Hours', 'closing_time'): ['12PM', '9PM'],
    ('Users_Compliments', 'number_of_compliments'): ['High', 'Uber'],
    ('Reviews', 'review_votes_useful'): ['Medium'],
}

NULL_SHARE = {
    ('Business', 'stars'): 0.15,
    ('Business', 'city'): 0.10,
    ('Business', 'state'): 0.10,
    ('Business', 'active'): 0.10,
    ('Business', 'review_count'): 0.10,
    ('Categories', 'category_name'): 0.10,
    ('Attributes', 'attribute_name'): 0.10,
    ('Compliments', 'compliment_type'): 0.10,
    ('Days', 'day_of_week'): 0.10,
    ('Years', 'actual_year'): 0.10,
    ('Business_Attributes', 'attribute_value'): 0.10,
    ('Business_Hours', 'opening_time'): 0.05,
    ('Business_Hours', 'closing_time'): 0.05,
    ('Reviews', 'review_stars'): 0.10,
    ('Reviews', 'review_votes_funny'): 0.10,
    ('Reviews', 'review_votes_useful'): 0.10,
    ('Reviews', 'review_votes_cool'): 0.10,
    ('Reviews', 'review_length'): 0.10,
    ('Tips', 'likes'): 0.10,
    ('Tips', 'tip_length'): 0.10,
    ('Users', 'user_yelping_since_year'): 0.10,
    ('Users', 'user_average_stars'): 0.10,
    ('Users', 'user_votes_funny'): 0.10,
    ('Users', 'user_votes_useful'): 0.10,
    ('Users', 'user_votes_cool'): 0.10,
    ('Users', 'user_review_count'): 0.10,
    ('Users', 'user_fans'): 0.10,
    ('Users_Compliments', 'number_of_compliments'): 0.10,
}
for _h in range(24):
    NULL_SHARE[('Checkins', 'label_time_%d' % _h)] = 0.10

DISTINCT_COLUMNS = {
    ('Business', 'city'), ('Business', 'stars'),
    ('Categories', 'category_name'), ('Users', 'user_yelping_since_year'),
    ('Reviews', 'review_length'),
}

TIE_COLUMNS = {
    ('Business', 'city'), ('Business', 'review_count'),
    ('Categories', 'category_name'),
    ('Users', 'user_fans'),
    ('Reviews', 'review_length'),
    ('Compliments', 'compliment_type'),
    ('Attributes', 'attribute_name'), ('Days', 'day_of_week'),
}

GROUP_COLUMNS = {
    ('Business', 'city'),
    ('Categories', 'category_name'),
    ('Attributes', 'attribute_name'),
}

DIFFERENT_VALUES = {
    ('Business', 'stars'), ('Reviews', 'review_stars'),
    ('Business', 'review_count'),
}

UNMATCHED_PARENTS = {
    'Business': ['Business_Categories', 'Reviews', 'Business_Attributes', 'Business_Hours',
                 'Checkins', 'Tips'],
    'Users': ['Reviews', 'Elite', 'Users_Compliments', 'Tips'],
    'Categories': ['Business_Categories'],
    'Attributes': ['Business_Attributes'],
    'Days': ['Business_Hours', 'Checkins'],
    'Years': ['Elite'],
    'Compliments': ['Users_Compliments'],
}

SHORT_TEXT = {
    ('Business', 'city'): ['Phoenix', 'Scottsdale', 'Glendale', 'Casa Grande', 'Peoria', 'Mesa',
                           'Tempe', 'Chandler', 'Gilbert', 'Anthem', 'Tolleson', 'Yuma',
                           'Sun City Anthem'],
    ('Business', 'review_count'): ['Low', 'Medium', 'High', 'Uber'],
    ('Users', 'user_average_stars'): ['1.0', '1.5', '2.0', '2.5', '3.0', '3.5', '4.0', '4.5', '5.0'],
    ('Attributes', 'attribute_name'): ['Alcohol', 'Waiter Service', 'Delivery', 'Attire',
                                       'Good for Kids', 'Take-out', 'Accepts Credit Cards',
                                       'Price Range', 'Open 24 Hours', 'Caters', 'Wi-Fi',
                                       'Accepts Insurance', 'Dogs Allowed'],
    ('Categories', 'category_name'): ['Active Life', 'Arts & Entertainment', 'Stadiums & Arenas',
                                      'Horse Racing', 'Tires', 'Automotive', 'Fashion', 'Shopping',
                                      'Food', 'Bars', 'Accessories', 'Pets', "Women's Clothing",
                                      "Men's Clothing", 'Mexican', 'Chinese', 'Filipino', 'Buffets',
                                      'Gyms', 'Hair Removal', 'Beauty & Spas', 'Local Services'],
    ('Business_Attributes', 'attribute_value'): ['none', 'full_bar', 'beer_and_wine', 'false',
                                                 'true', 'casual', 'dressy', 'formal', 'no',
                                                 'waiter service'],
}
