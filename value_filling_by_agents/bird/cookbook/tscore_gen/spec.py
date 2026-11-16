"""Specification constants (tscore_gen/specification.json) implemented by construction."""

TABLE_SIZES = {'Ingredient': 40, 'Recipe': 40, 'Nutrition': 40, 'Quantity': 80}

NULL_RATE = {
    ('Ingredient', 'category'): 0.0,
    ('Ingredient', 'name'): 0.0,
    ('Ingredient', 'plural'): 0.782,
    ('Recipe', 'title'): 0.148,
    ('Recipe', 'subtitle'): 0.966,
    ('Recipe', 'servings'): 0.148,
    ('Recipe', 'yield_unit'): 0.885,
    ('Recipe', 'prep_min'): 0.148,
    ('Recipe', 'cook_min'): 0.148,
    ('Recipe', 'stnd_min'): 0.148,
    ('Recipe', 'source'): 0.38,
    ('Recipe', 'intro'): 0.682,
    ('Recipe', 'directions'): 0.21,
    ('Nutrition', 'protein'): 0.0,
    ('Nutrition', 'carbo'): 0.0,
    ('Nutrition', 'alcohol'): 0.0,
    ('Nutrition', 'total_fat'): 0.0,
    ('Nutrition', 'sat_fat'): 0.0,
    ('Nutrition', 'cholestrl'): 0.0,
    ('Nutrition', 'sodium'): 0.0,
    ('Nutrition', 'iron'): 0.0,
    ('Nutrition', 'vitamin_c'): 0.0,
    ('Nutrition', 'vitamin_a'): 0.0,
    ('Nutrition', 'fiber'): 0.0,
    ('Nutrition', 'pcnt_cal_carb'): 0.0,
    ('Nutrition', 'pcnt_cal_fat'): 0.0,
    ('Nutrition', 'pcnt_cal_prot'): 0.0,
    ('Nutrition', 'calories'): 0.0,
    ('Quantity', 'recipe_id'): 0.005,
    ('Quantity', 'ingredient_id'): 0.005,
    ('Quantity', 'max_qty'): 0.005,
    ('Quantity', 'min_qty'): 0.005,
    ('Quantity', 'unit'): 0.005,
    ('Quantity', 'preparation'): 0.628,
    ('Quantity', 'optional'): 0.005,
}
NULL_BAND = {
    ('Quantity', 'recipe_id'): (0.05, 0.30),
    ('Quantity', 'max_qty'): (0.05, 0.30),
    ('Quantity', 'optional'): (0.05, 0.30),
}

DUP_SHARE = {
    ('Ingredient', 'name'): 0.35,
    ('Quantity', 'recipe_id'): 0.35,
    ('Recipe', 'title'): 0.35,
    ('Quantity', 'quantity_id'): 0.35,
}

BOUNDARY_TEXT = {
    ('Ingredient', 'name'): ['1% lowfat milk', '1% LOWFAT MILK', 'lima beans', 'LIMA BEANS'],
    ('Recipe', 'title'): ['Raspberry Chiffon Pie', 'raspberry chiffon pie',
                          'Fresh Apricot Bavarian', 'fresh apricot bavarian',
                          'RasPie', 'raspie'],
    ('Quantity', 'unit'): ['cup(s)', 'CUP(S)'],
}
BOUNDARY_INT = {
    ('Quantity', 'recipe_id'): [1396, 1397, 1398, 1435, 1436, 1437],
    ('Recipe', 'recipe_id'): [1396, 1397, 1398, 1435, 1436, 1437],
    ('Recipe', 'servings'): [6, 7, 8],
}
BOUNDARY_REAL = {
    ('Nutrition', 'sodium'): [4.99, 5.0, 5.01],
    ('Nutrition', 'vitamin_a'): [-0.01, 0.0, 0.01],
    ('Nutrition', 'alcohol'): [-0.01, 0.0, 0.01],
}
LIKE_NEAR = {('Ingredient', 'name'): ['%seedless red grapes%']}

TIE_TARGETS = {
    ('Nutrition', 'sat_fat'): ('total_fat - sat_fat', 'DESC', 1),
    ('Nutrition', 'total_fat'): ('total_fat - sat_fat', 'DESC', 1),
    ('Nutrition', 'cholestrl'): ('total_fat - cholestrl', 'DESC', 1),
    ('Nutrition', 'iron'): ('total_fat - iron', 'DESC', 1),
    ('Nutrition', 'pcnt_cal_fat'): ('pcnt_cal_fat - sat_fat', 'DESC', 1),
    ('Nutrition', 'pcnt_cal_prot'): (None, 'unordered', 1),
}

DIFF_VALUE_COLUMNS = [('Nutrition', 'calories'), ('Nutrition', 'vitamin_c'),
                      ('Nutrition', 'carbo'), ('Nutrition', 'vitamin_a')]

ENUM_POOL = {
    ('Quantity', 'optional'): ['TRUE', 'FALSE'],
    ('Quantity', 'unit'): ['cup(s)', 'teaspoon(s)', 'tablespoon(s)', 'pound(s)', 'ounce(s)',
                           'packet(s)', 'envelope(s)', 'can(s)', 'clove(s)', 'slice(s)',
                           '14 oz. can(s)', '21 oz. can(s)', 'quart(s)', 'pint(s)', 'gram(s)'],
    ('Ingredient', 'category'): ['dairy', 'Mexican products', 'cereals', 'breads',
                                 'fresh vegetables', 'miscellaneous', 'vinegars',
                                 'baking products', 'fruits', 'meats', 'seafood',
                                 'frozen foods', 'beverages', 'spices', 'oils'],
    ('Ingredient', 'plural'): ['s', 'es', ''],
}

RANGES = {
    ('Ingredient', 'ingredient_id'): (1, None, True),
    ('Recipe', 'recipe_id'): (1, None, True),
    ('Recipe', 'servings'): (1, None, True),
    ('Recipe', 'prep_min'): (0, None, True),
    ('Recipe', 'cook_min'): (0, None, True),
    ('Recipe', 'stnd_min'): (0, None, True),
    ('Nutrition', 'recipe_id'): (1, None, True),
    ('Nutrition', 'protein'): (0.0, None, False),
    ('Nutrition', 'carbo'): (0.0, None, False),
    ('Nutrition', 'alcohol'): (0.0, None, False),
    ('Nutrition', 'total_fat'): (0.0, None, False),
    ('Nutrition', 'sat_fat'): (0.0, None, False),
    ('Nutrition', 'cholestrl'): (0.0, None, False),
    ('Nutrition', 'sodium'): (0.0, None, False),
    ('Nutrition', 'iron'): (0.0, None, False),
    ('Nutrition', 'vitamin_c'): (0.0, None, False),
    ('Nutrition', 'vitamin_a'): (0.0, None, False),
    ('Nutrition', 'fiber'): (0.0, None, False),
    ('Nutrition', 'pcnt_cal_carb'): (0.0, 100.0, False),
    ('Nutrition', 'pcnt_cal_fat'): (0.0, 100.0, False),
    ('Nutrition', 'pcnt_cal_prot'): (0.0, 100.0, False),
    ('Nutrition', 'calories'): (0.0, None, False),
    ('Quantity', 'quantity_id'): (1, None, True),
    ('Quantity', 'max_qty'): (0.0, None, False),
    ('Quantity', 'min_qty'): (0.0, None, False),
}

TEXT_POOL = {
    ('Recipe', 'title'): ['Raspberry Chiffon Pie', 'Apricot Yogurt Parfaits',
                          'Fresh Apricot Bavarian', 'Fresh Peaches', 'Canned Cherry Crisp',
                          'Low Calorie Blueberry Meringue Tarts',
                          'Chocolate Cream Cheese Frosting', 'Sweet Cherry Ice'],
    ('Recipe', 'subtitle'): ['with Banana Cream Whip', 'a La Creme',
                             'with Raspberry Yogurt Mint Sauce', 'with Apricot Sauce',
                             'with Orange Custard Sauce', 'with Pecans',
                             'with Yogurt Herb Sauce', 'with Lemon and Parmesan'],
    ('Recipe', 'yield_unit'): ['1 pie', '8 tarts', '2 quarts', '10 popsicles', '1 cake',
                               '2 cups', '1 3-layer cake', '2'],
    ('Recipe', 'source'): ['The California Tree Fruit Agreement',
                           'Produce for Better Health Foundation and 5 a Day',
                           'The California Apricot Advisory Board',
                           'The Cherry Marketing Institute',
                           'North American Blueberry Council',
                           'Chocolate Manufacturers Association',
                           'Northwest Cherry Growers', 'New Zealand Fruit Company'],
    ('Recipe', 'intro'): ['Serve in stemmed glasses and top with sliced apricots for elegant endings.',
                          'For a quick, low-cal dessert, serve this on other sliced fruit such as berries.',
                          'Your microwave turns a can of cherry pie filling into a quick hot dessert.',
                          'No one could ever guess that these tasty tarts are low in calories.',
                          'Cholesterol-free, lowfat and refreshing.',
                          'A sweet twist to a popular dish.',
                          'An old-fashioned dessert made up-to-date by cutting the fat.',
                          'Great sprinkled on frozen yogurt.'],
    ('Recipe', 'directions'): ['Preheat oven to 375 degrees F. Combine crumbs, butter and sugar.',
                               'Sprinkle gelatin over juice and let stand for 5 minutes to soften.',
                               'Drop fruit into boiling water to cover. Return to boil and simmer.',
                               'Beat egg white until foamy. Add banana, sugar and lemon juice.',
                               'Pour pie filling into a microwave-safe dish. Sprinkle with extract.',
                               'Beat egg whites until very stiff. Gradually beat in dry milk powder.',
                               'Place cream cheese, butter, vanilla, cream and cocoa in blender.',
                               'Puree cherries in blender. Combine with applesauce and sugar.'],
    ('Ingredient', 'name'): ['1% lowfat cottage cheese', '1% lowfat milk',
                             '10-inch flour tortilla', '100% bran cereal', '2% lowfat milk',
                             '3-inch round pita bread', '4-inch diameter rye roll',
                             '6-inch corn tortilla', 'seedless red grapes', 'lima beans'],
    ('Quantity', 'preparation'): ['melted', 'or water', 'divided', 'crushed', 'sliced',
                                  'ripe', 'uncooked', 'toasted', 'chopped', 'drained'],
}
