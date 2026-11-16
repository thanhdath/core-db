"""The generation specification, encoded as data (no rule is evaluated with SQL)."""

RANGES = {
    ('borders', 'Length'): ('real', 0.0, 10000000.0),
    ('city', 'Population'): ('int', 0, 1000000000),
    ('city', 'Longitude'): ('lon', -180.0, 180.0),
    ('city', 'Latitude'): ('lat', -90.0, 90.0),
    ('continent', 'Area'): ('real', 0.0, 10000000.0),
    ('country', 'Area'): ('real', 0.0, 10000000.0),
    ('country', 'Population'): ('int', 0, 1000000000),
    ('desert', 'Area'): ('real', 0.0, 10000000.0),
    ('desert', 'Longitude'): ('lon', -180.0, 180.0),
    ('desert', 'Latitude'): ('lat', -90.0, 90.0),
    ('economy', 'GDP'): ('real', 0.0, 10000000.0),
    ('economy', 'Agriculture'): ('pct', 0.0, 100.0),
    ('economy', 'Service'): ('pct', 0.0, 100.0),
    ('economy', 'Industry'): ('pct', 0.0, 100.0),
    ('economy', 'Inflation'): ('real', -100.0, 1000.0),
    ('encompasses', 'Percentage'): ('pct', 0.0, 100.0),
    ('ethnicGroup', 'Percentage'): ('pct', 0.0, 100.0),
    ('island', 'Area'): ('real', 0.0, 10000000.0),
    ('island', 'Height'): ('real', 0.0, 10000000.0),
    ('island', 'Longitude'): ('lon', -180.0, 180.0),
    ('island', 'Latitude'): ('lat', -90.0, 90.0),
    ('lake', 'Area'): ('real', 0.0, 10000000.0),
    ('lake', 'Depth'): ('real', 0.0, 10000000.0),
    ('lake', 'Altitude'): ('real', -1000.0, 10000000.0),
    ('lake', 'Longitude'): ('lon', -180.0, 180.0),
    ('lake', 'Latitude'): ('lat', -90.0, 90.0),
    ('language', 'Percentage'): ('pct', 0.0, 100.0),
    ('mountain', 'Height'): ('real', 0.0, 10000000.0),
    ('mountain', 'Longitude'): ('lon', -180.0, 180.0),
    ('mountain', 'Latitude'): ('lat', -90.0, 90.0),
    ('population', 'Population_Growth'): ('real', -100.0, 100.0),
    ('population', 'Infant_Mortality'): ('real', 0.0, 10000000.0),
    ('province', 'Population'): ('int', 0, 1000000000),
    ('province', 'Area'): ('real', 0.0, 10000000.0),
    ('religion', 'Percentage'): ('pct', 0.0, 100.0),
    ('river', 'Length'): ('real', 0.0, 10000000.0),
    ('river', 'SourceLongitude'): ('lon', -180.0, 180.0),
    ('river', 'SourceLatitude'): ('lat', -90.0, 90.0),
    ('river', 'EstuaryLongitude'): ('lon', -180.0, 180.0),
    ('river', 'EstuaryLatitude'): ('lat', -90.0, 90.0),
    ('river', 'SourceAltitude'): ('real', -1000.0, 10000000.0),
    ('sea', 'Depth'): ('real', 0.0, 10000000.0),
}

ENUMS = {
    ('isMember', 'Type'): ('member', 'nonregional member', 'observer', 'National Society',
                           'Part I', 'Category I', 'National Olympic Committee'),
    ('island', 'Type'): ('volcanic', 'lime', 'coral', 'atoll'),
    ('lake', 'Type'): ('artificial', 'salt', 'caldera', 'impact', 'acid', 'crater'),
    ('target', 'Target'): ('Christian', 'non-Christian'),
}

TABLE_SIZES = {
    'continent': 5, 'country': 40, 'province': 80, 'city': 120, 'economy': 40,
    'population': 40, 'politics': 40, 'target': 40, 'encompasses': 45,
    'ethnicGroup': 60, 'language': 50, 'religion': 60, 'borders': 50, 'desert': 15,
    'island': 30, 'lake': 25, 'mountain': 30, 'river': 30, 'sea': 15,
    'organization': 30, 'isMember': 200, 'geo_desert': 30, 'geo_estuary': 30,
    'geo_island': 30, 'geo_lake': 30, 'geo_mountain': 30, 'geo_river': 40,
    'geo_sea': 40, 'geo_source': 30, 'islandIn': 40, 'located': 60, 'locatedOn': 50,
    'mergesWith': 20, 'mountainOnIsland': 20,
}

NULL_TARGETS = {
    'country.Capital', 'country.Province', 'city.Population', 'city.Longitude',
    'city.Latitude', 'economy.GDP', 'economy.Agriculture', 'economy.Service',
    'economy.Industry', 'economy.Inflation', 'island.Islands', 'island.Area',
    'island.Height', 'island.Type', 'lake.Depth', 'lake.Altitude', 'lake.Type',
    'lake.River', 'river.River', 'river.Lake', 'river.Sea', 'river.Mountains',
    'river.SourceAltitude', 'organization.City', 'organization.Country',
    'organization.Province', 'organization.Established', 'politics.Independence',
    'politics.Dependent', 'politics.Government', 'population.Population_Growth',
    'population.Infant_Mortality', 'province.Area', 'province.Capital',
    'province.CapProv', 'islandIn.Sea', 'islandIn.Lake', 'islandIn.River',
    'located.River', 'located.Lake', 'located.Sea',
    'mountain.Mountains', 'mountain.Type', 'mountain.Height', 'mountain.Longitude',
    'mountain.Latitude', 'borders.Length', 'continent.Area', 'country.Area',
    'country.Population', 'encompasses.Percentage', 'ethnicGroup.Percentage',
    'isMember.Type', 'language.Percentage', 'province.Population',
    'religion.Percentage', 'sea.Depth', 'target.Target', 'desert.Area',
    'desert.Longitude', 'desert.Latitude', 'island.Longitude', 'island.Latitude',
    'lake.Longitude', 'lake.Latitude', 'river.Length', 'river.SourceLongitude',
    'river.SourceLatitude', 'river.EstuaryLongitude', 'river.EstuaryLatitude',
    'city.Province', 'city.Country', 'organization.City',
}

BOUNDARIES = {
    'country.Population': [4999999, 5000000, 5000001, 9999999, 10000000, 10000001],
    'country.Area': [99999.9, 100000.0, 100000.1, 9999999.9, 10000000.0, 10000000.1],
    'economy.GDP': [499998.99, 499999.0, 499999.01, 999999.99, 1000000.0, 1000000.01],
    'population.Population_Growth': [-0.01, 0.0, 0.01],
    'mountain.Height': [999.0, 1000.0, 1001.0],
    'sea.Depth': [458.0, 459.0, 460.0],
}

DUP_TARGETS = {'economy.Country', 'geo_mountain.Mountain', 'organization.City',
               'ethnicGroup.Name', 'language.Name', 'religion.Name'}
TIE_TARGETS = {'country.Name', 'country.Population', 'organization.Country',
               'politics.Country', 'economy.GDP', 'country.Area', 'organization.Name'}
GROUP_TARGETS = {'country.Name', 'country.Code', 'organization.Country',
                 'encompasses.Continent'}

UNMATCHED_JOIN = {'country.Code', 'city.Country', 'province.Country', 'economy.Country',
                  'organization.Country', 'politics.Country', 'encompasses.Country',
                  'city.Province', 'province.Name', 'mountain.Name',
                  'geo_mountain.Mountain', 'organization.City', 'city.Name'}

STRING_VARIANTS = {
    'country.Name': ['United States', 'united states', 'Japan', 'japan', 'Italy', 'italy'],
    'city.Name': ['Baghdad', 'baghdad', 'Orleans', 'orleans', 'Paris', 'paris'],
    'continent.Name': ['Asia', 'asia', 'European', 'european', 'Africa', 'africa'],
    'mountain.Name': ['Kerinci', 'kerinci', 'Mountain', 'mountain'],
    'organization.City': ['Washington', 'washington', 'London', 'london', 'Paris', 'paris'],
    'ethnicGroup.Name': ['African', 'Afrian'],
    'language.Name': ['Bosnian', 'Bon'],
    'located.Province': ['Canary Islands', 'Canary ', ' Isl'],
}
