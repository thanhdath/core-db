"""Specification constants (generation specification, by construction)."""

TABLE_SIZES = {'station': 12, 'train': 11, 'train_station': 11}

ENUMS = {
    ('train', 'Service'): ['Daily'],
}

NAME_POOL = {
    'station': ['London Waterloo', 'London Victoria', 'London Bridge', 'London Liverpool Street',
                'London Euston', 'London Charing Cross', 'Birmingham New Street', "London King's Cross",
                'Glasgow Central', 'Manchester Piccadilly', 'Leeds', 'Edinburgh Waverley'],
    'train': ['Ananthapuri Express', 'Guruvayur Express', 'Jayanthi Janatha Express', 'Island Express',
              'Madurai Fast Passenger', 'Quilon Fast Passenger', 'Parasuram Express'],
}
LOCATION_POOL = ['London', 'Birmingham', 'Glasgow']
SERVICE_POOL = ['South Western Main Line West of England Main Line', 'Brighton Main Line Chatham Main Line',
                'South Eastern Main Line Thameslink', 'Great Eastern Main Line West Anglia Main Line',
                'West Coast Main Line', 'South Eastern Main Line', 'West Coast Main Line Cross Country Route',
                'East Coast Main Line']

BOUNDARIES = {
    ('station', 'Annual_entry_exit'): [24.999, 25.0, 25.001],
    ('station', 'Total_Passengers'): [8.999, 9.0, 9.001, 24.999, 25.0, 25.001],
}

GROUP_SIZE_COLUMNS = [('station', 'Station_ID'), ('station', 'Name'), ('station', 'Location'),
                      ('station', 'Main_Services'), ('station', 'Number_of_Platforms'),
                      ('train_station', 'Station_ID')]

AGGREGATE_COUNT_VALUES = [1, 2, 3]

TIE_COLUMNS = [('train_station', 'Station_ID'), ('station', 'Name'), ('station', 'Location'),
               ('station', 'Annual_interchanges'), ('station', 'Main_Services'), ('train', 'Time')]
TIME_LIMIT_TIE = 2

DISTINCT_DUP_COLUMNS = [('station', 'Name'), ('train_station', 'Train_ID'), ('train', 'Name')]

NULL_SHARE = 0.10
NULLABLE_COLUMNS = [
    ('station', 'Name'), ('station', 'Annual_entry_exit'), ('station', 'Annual_interchanges'),
    ('station', 'Total_Passengers'), ('station', 'Location'), ('station', 'Main_Services'),
    ('station', 'Number_of_Platforms'), ('train', 'Name'), ('train', 'Time'), ('train', 'Service'),
]

TOTAL_PASSENGERS_FORMULA = ('station', 'Total_Passengers', 'Annual_entry_exit', 'Annual_interchanges')
TOTAL_PASSENGERS_TOL = 0.01

RANGES = {
    ('station', 'Station_ID'): (1, 10 ** 6),
    ('station', 'Annual_entry_exit'): (0.0, 200.0),
    ('station', 'Annual_interchanges'): (0.0, 200.0),
    ('station', 'Total_Passengers'): (0.0, 400.0),
    ('station', 'Number_of_Platforms'): (1, 200),
    ('train', 'Train_ID'): (1, 10 ** 6),
    ('train_station', 'Train_ID'): (1, 10 ** 6),
    ('train_station', 'Station_ID'): (1, 10 ** 6),
}
