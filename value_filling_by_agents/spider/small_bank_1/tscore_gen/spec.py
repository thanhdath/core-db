"""Specification constants and helpers (implemented by construction, never by SQL)."""
import re

TABLE_SIZES = {'ACCOUNTS': 7, 'SAVINGS': 6, 'CHECKING': 7}

NON_NEGATIVE = {('SAVINGS', 'balance'), ('CHECKING', 'balance')}
POSITIVE = {('ACCOUNTS', 'custid')}

BALANCE_BANDS = [(0.0, 1000.0), (1000.0, 100000.0), (100000.0, 1e9)]

SURNAMES = ['Brown', 'Wang', "O'mahony", 'Weeks', 'Granger', 'Porter', 'Wesley',
            'Smith', 'Jones', 'Miller', 'Davis', 'Garcia', 'Rodriguez', 'Wilson',
            'Martinez', 'Anderson', 'Taylor', 'Thomas', 'Hernandez', 'Moore',
            'Martin', 'Jackson', 'Thompson', 'White', 'Lopez', 'Lee', 'Gonzalez',
            'Harris', 'Clark', 'Lewis', 'Robinson', 'Walker', 'Perez', 'Hall',
            'Young', 'Allen', 'Sanchez', 'Wright', 'King', 'Scott', 'Green',
            'Baker', 'Adams', 'Nelson', 'Hill', 'Ramirez', 'Campbell', 'Mitchell',
            'Roberts', 'Carter', 'Phillips', 'Evans', 'Turner', 'Torres', 'Parker',
            'Collins', 'Edwards', 'Stewart', 'Flores', 'Morris', 'Nguyen', 'Murphy',
            'Rivera', 'Cook', 'Rogers', 'Morgan', 'Peterson', 'Cooper', 'Reed',
            'Bailey', 'Bell', 'Gomez', 'Kelly', 'Howard', 'Ward', 'Cox', 'Diaz',
            'Richardson', 'Wood', 'Watson', 'Brooks', 'Bennett', 'Gray', 'James',
            'Reyes', 'Cruz', 'Hughes', 'Price', 'Myers', 'Long', 'Foster', 'Sanders',
            'Ross', 'Morales', 'Powell', 'Sullivan', 'Russell', 'Ortiz', 'Jenkins',
            'Perry', 'Butler', 'Barnes', 'Fisher', 'Henderson', 'Coleman', 'Simmons',
            'Patterson', 'Jordan', 'Reynolds', 'Hamilton', 'Graham', 'Kim', 'Gonzales',
            'Alexander', 'Ramos', 'Wallace', 'Griffin', 'West', 'Cole', 'Hayes',
            'Chavez', 'Gibson', 'Bryant', 'Ellis', 'Stevens', 'Murray', 'Ford',
            'Marshall', 'Owens', 'McDonald', 'Harrison', 'Ruiz', 'Kennedy', 'Wells',
            'Alvarez', 'Woods', 'Mendoza', 'Castillo', 'Olson', 'Webb', 'Washington',
            'Tucker', 'Freeman', 'Burns', 'Henry', 'Vasquez', 'Snyder', 'Simpson',
            'Crawford', 'Jimenez', 'Porter', 'Mason', 'Shaw', 'Gordon', 'Wagner',
            'Hunter', 'Romero', 'Hicks', 'Dixon', 'Hunt', 'Palmer', 'Robertson',
            'Black', 'Holmes', 'Stone', 'Meyer', 'Boyd', 'Mills', 'Warren', 'Fox',
            'Rose', 'Rice', 'Moreno', 'Schmidt', 'Patel', 'Ferguson', 'Nichols',
            'Herrera', 'Medina', 'Ryan', 'Fernandez', 'Weaver', 'Daniels', 'Stephens',
            'Gardner', 'Payne', 'Kelley', 'Dunn', 'Pierce', 'Arnold', 'Tran',
            'Spencer', 'Peters', 'Hawkins', 'Grant', 'Hansen', 'Castro', 'Hoffman',
            'Hart', 'Elliott', 'Cunningham', 'Knight', 'Bradley', 'Carroll', 'Hudson',
            'Duncan', 'Armstrong', 'Berry', 'Andrews', 'Johnston', 'Ray', 'Lane',
            'Riley', 'Carpenter', 'Perkins', 'Aguilar', 'Silva', 'Richards', 'Willis',
            'Matthews', 'Chapman', 'Lawrence', 'Garza', 'Vargas', 'Watkins', 'Wheeler',
            'Larson', 'Carlson', 'Harper', 'George', 'Greene', 'Burke', 'Guzman',
            'Morrison', 'Munoz', 'Jacobs', 'Obrien', 'Lawson', 'Franklin', 'Lynch',
            'Bishop', 'Carr', 'Salazar', 'Austin', 'Mendez', 'Gilbert', 'Jensen',
            'Williamson', 'Montgomery', 'Harvey', 'Oliver', 'Howell', 'Dean', 'Hanson',
            'Weber', 'Garrett', 'Sims', 'Burton', 'Fuller', 'Soto', 'McCoy', 'Welch',
            'Chen', 'Schultz', 'Walters', 'Reid', 'Fields', 'Walsh', 'Little',
            'Fowler', 'Bowman', 'Davidson', 'May', 'Day', 'Schneider', 'Newman',
            'Brewer', 'Lucas', 'Holland', 'Wong', 'Banks', 'Santos', 'Curtis',
            'Pearson', 'Delgado', 'Valdez', 'Pena', 'Rios', 'Douglas', 'Sandoval',
            'Barrett', 'Hopkins', 'Keller', 'Guerrero', 'Stanley', 'Bates', 'Alvarado',
            'Beck', 'Ortega', 'Wade', 'Estrada', 'Contreras', 'Barnett', 'Caldwell',
            'Santiago', 'Lambert', 'Powers', 'Chambers', 'Nunez', 'Craig', 'Leonard',
            'Lowe', 'Rhodes', 'Byrd', 'Gregory', 'Shelton', 'Frazier', 'Becker',
            'Maldonado', 'Fleming', 'Vega', 'Sutton', 'Cohen', 'Jennings', 'Parks',
            'McDaniel', 'Watts', 'Barker', 'Norris', 'Vaughn', 'Vazquez', 'Holt',
            'Schwartz', 'Steele', 'Benson', 'Neal', 'Dominguez', 'Horton', 'Terry',
            'Wolfe', 'Hale', 'Lyons', 'Graves', 'Haynes', 'Miles', 'Park', 'Warner',
            'Padilla', 'Bush', 'Thornton', 'McCarthy', 'Mann', 'Zimmerman', 'Erickson',
            'Fletcher', 'McKinney', 'Page', 'Dawson', 'Joseph', 'Marquez', 'Reeves',
            'Klein', 'Espinoza', 'Baldwin', 'Moran', 'Love', 'Robbins', 'Higgins',
            'Ball', 'Cortez', 'Le', 'Griffith', 'Bowen', 'Sharp', 'Cummings', 'Ramsey',
            'Hardy', 'Swanson', 'Barber', 'Acosta', 'Luna', 'Chandler', 'Blair',
            'Daniel', 'Cross', 'Simon', 'Dennis', 'Oconnor', 'Quinn', 'Gross', 'Navarro',
            'Moss', 'Fitzgerald', 'Doyle', 'McLaughlin', 'Rojas', 'Rodgers', 'Stevenson',
            'Singh', 'Yang', 'Figueroa', 'Harmon', 'Newton', 'Paul', 'Manning',
            'Garner', 'McGee', 'Reese', 'Francis', 'Burgess', 'Adkins', 'Goodman',
            'Curry', 'Brady', 'Christensen', 'Potter', 'Walton', 'Goodwin', 'Walton',
            'Bond', 'Huang', 'Berger', 'Wise', 'Fischer', 'Campos', 'Velez', 'Hines',
            'Blankenship', 'Cervantes', 'Baxter', 'Cline', 'Cantu', 'Mercado', 'Willis',
            'Sosa', 'Blanchard', 'Huff', 'Clayton', 'Moody', 'Mayer', 'Alston',
            'Blevins', 'Farmer', 'French', 'Woodward', 'Herring', 'McIntosh', 'Koch',
            'Bauer', 'Barr', 'Rivas', 'Kinney', 'Holder', 'Crosby', 'Booth', 'Mata',
            'Hodge', 'Barrera', 'McCall', 'Hess', 'Benton', 'Chase', 'Cobb', 'Cuevas',
            'Clements', 'Cochran', 'Bautista', 'Bowers', 'Boyle', 'Brennan', 'Briggs',
            'Brock', 'Brooks', 'Browning', 'Bryan', 'Buck', 'Buckley', 'Bullock',
            'Burch', 'Burgos', 'Burnett', 'Burris', 'Burt', 'Byers', 'Cabrera',
            'Cain', 'Calderon', 'Calhoun', 'Callahan', 'Camacho', 'Cameron', 'Cannon',
            'Cardenas', 'Carlisle', 'Carson', 'Case', 'Casey', 'Castaneda', 'Cervantes',
            'Chaney', 'Chang', 'Chase', 'Chavez', 'Chen', 'Cherry', 'Choi', 'Christensen',
            'Church', 'Cisneros', 'Clarke', 'Clay', 'Clayton', 'Clements', 'Cline',
            'Cobb', 'Cochran', 'Coffey', 'Cohen', 'Cole', 'Coleman', 'Collier',
            'Collins', 'Colon', 'Combs', 'Compton', 'Conley', 'Conner', 'Conrad',
            'Contreras', 'Conway', 'Cook', 'Cooke', 'Cooley', 'Cooper', 'Copeland',
            'Cordova', 'Cortez', 'Costa', 'Cote', 'Cotton', 'Cox', 'Craft', 'Craig',
            'Crane', 'Crawford', 'Crosby', 'Cross', 'Cruz', 'Cuevas', 'Cummings',
            'Cunningham', 'Curry', 'Curtis', 'Dalton', 'Daniel', 'Daniels', 'Daugherty',
            'Davenport', 'David', 'Davidson', 'Davis', 'Dawson', 'Day', 'Dean',
            'Decker', 'Delacruz', 'Delaney', 'Deleon', 'Delgado', 'Dennis', 'Diaz',
            'Dickerson', 'Dickson', 'Dillon', 'Dixon', 'Dodson', 'Dominguez', 'Donaldson',
            'Donovan', 'Dorsey', 'Dougherty', 'Douglas', 'Downs', 'Doyle', 'Drake',
            'Duarte', 'Dudley', 'Duffy', 'Duke', 'Duncan', 'Dunlap', 'Dunn', 'Duran',
            'Durham', 'Dyer', 'Eaton', 'Edwards', 'Elliott', 'Ellis', 'Ellison',
            'English', 'Erickson', 'Escobar', 'Esparza', 'Espinoza', 'Estes', 'Estrada',
            'Evans', 'Everett', 'Ewing', 'Farley', 'Farmer', 'Farrell', 'Faulkner',
            'Ferguson', 'Fernandez', 'Fields', 'Figueroa', 'Finley', 'Fischer', 'Fisher',
            'Fitzgerald', 'Fitzpatrick', 'Fleming', 'Fletcher', 'Flores', 'Flowers',
            'Floyd', 'Flynn', 'Foley', 'Forbes', 'Ford', 'Foster', 'Fowler', 'Fox',
            'Francis', 'Franco', 'Frank', 'Franklin', 'Frazier', 'Frederick', 'Freeman',
            'French', 'Frey', 'Friedman', 'Fritz', 'Frost', 'Fry', 'Frye', 'Fuentes',
            'Fuller', 'Gaines', 'Gallagher', 'Gallegos', 'Galloway', 'Galvan', 'Gamble',
            'Garcia', 'Gardner', 'Garner', 'Garrett', 'Garrison', 'Garza', 'Gates',
            'Gay', 'Gentry', 'George', 'Gibbs', 'Gibson', 'Gilbert', 'Giles', 'Gill',
            'Gillespie', 'Gilmore', 'Glass', 'Glenn', 'Glover', 'Goddard', 'Godfrey',
            'Golden', 'Gomez', 'Gonzales', 'Gonzalez', 'Good', 'Goodman', 'Goodwin',
            'Gordon', 'Gould', 'Graham', 'Grant', 'Graves', 'Gray', 'Green', 'Greene',
            'Greer', 'Gregory', 'Griffin', 'Griffith', 'Grimes', 'Gross', 'Guerra',
            'Guerrero', 'Guzman', 'Hahn', 'Hale', 'Haley', 'Hall', 'Hamilton', 'Hammond',
            'Hampton', 'Haney', 'Hanna', 'Hansen', 'Hanson', 'Hardin', 'Harding',
            'Hardy', 'Harmon', 'Harper', 'Harrell', 'Harrington', 'Harris', 'Harrison',
            'Hart', 'Hartman', 'Harvey', 'Hatfield', 'Hawkins', 'Hayden', 'Hayes',
            'Haynes', 'Hays', 'Heath', 'Hebert', 'Henderson', 'Hendricks', 'Hendrix',
            'Henry', 'Hensley', 'Henson', 'Herman', 'Hernandez', 'Herrera', 'Herring',
            'Hess', 'Hester', 'Hickman', 'Hicks', 'Higgins', 'High', 'Hill', 'Hines',
            'Hinton', 'Ho', 'Hobbs', 'Hodge', 'Hodges', 'Hoffman', 'Hogan', 'Holden',
            'Holder', 'Holland', 'Holloway', 'Holman', 'Holmes', 'Holt', 'Hood',
            'Hooper', 'Hoover', 'Hopkins', 'Horn', 'Horne', 'Horton', 'House',
            'Houston', 'Howard', 'Howe', 'Howell', 'Hubbard', 'Huber', 'Hudson',
            'Huerta', 'Huff', 'Huffman', 'Hughes', 'Hull', 'Humphrey', 'Hunt',
            'Hunter', 'Hurley', 'Hurst', 'Hutchinson', 'Huynh', 'Ibarra', 'Ingram',
            'Irwin', 'Jackson', 'Jacobs', 'Jacobson', 'James', 'Jarvis', 'Jefferson',
            'Jenkins', 'Jennings', 'Jensen', 'Jimenez', 'Johns', 'Johnson', 'Johnston',
            'Jones', 'Jordan', 'Joseph', 'Joyce', 'Juarez', 'Kaiser', 'Kane', 'Kaufman',
            'Keith', 'Keller', 'Kelley', 'Kelly', 'Kemp', 'Kennedy', 'Kent', 'Kerr',
            'Key', 'Kidd', 'Kim', 'King', 'Kinney', 'Kirby', 'Kirk', 'Klein', 'Kline',
            'Knapp', 'Knight', 'Knox', 'Koch', 'Kramer', 'Krause', 'Krueger', 'Lam',
            'Lamb', 'Lambert', 'Landry', 'Lane', 'Lang', 'Langley', 'Lara', 'Larsen',
            'Larson', 'Lawrence', 'Lawson', 'Le', 'Leach', 'Leblanc', 'Lee', 'Leon',
            'Leonard', 'Lester', 'Levine', 'Levy', 'Lewis', 'Lindsay', 'Lindsey',
            'Little', 'Livingston', 'Lloyd', 'Logan', 'Long', 'Lopez', 'Love', 'Lowe',
            'Lowery', 'Lozano', 'Lucas', 'Lucero', 'Luna', 'Lutz', 'Lynch', 'Lynn',
            'Lyons', 'Macdonald', 'Macias', 'Mack', 'Madden', 'Maddox', 'Mahoney',
            'Maldonado', 'Malone', 'Mann', 'Manning', 'Marks', 'Marquez', 'Marsh',
            'Marshall', 'Martin', 'Martinez', 'Mason', 'Massey', 'Mata', 'Mathews',
            'Mathis', 'Matthews', 'Maxwell', 'May', 'Mayer', 'Maynard', 'Mayo',
            'Mays', 'McBride', 'McCann', 'McCarthy', 'McClain', 'McClellan', 'McClure',
            'McConnell', 'McCormick', 'McCoy', 'McCullough', 'McDaniel', 'McDonald',
            'McDowell', 'McFarland', 'McGee', 'McGuire', 'McIntosh', 'McKay',
            'McKenzie', 'McKinney', 'McLaughlin', 'McLean', 'McLeod', 'McMahon',
            'McMillan', 'McNeil', 'McPherson', 'Meadows', 'Medina', 'Mejia', 'Melendez',
            'Melton', 'Mendez', 'Mendoza', 'Mercado', 'Mercer', 'Merritt', 'Meyer',
            'Meyers', 'Michael', 'Middleton', 'Miles', 'Miller', 'Mills', 'Miranda',
            'Mitchell', 'Molina', 'Monroe', 'Montes', 'Montgomery', 'Montoya', 'Moody',
            'Moon', 'Mooney', 'Moore', 'Mora', 'Morales', 'Moran', 'Moreno', 'Morgan',
            'Morris', 'Morrison', 'Morrow', 'Morse', 'Morton', 'Moses', 'Mosley',
            'Moss', 'Moyer', 'Mueller', 'Mullen', 'Mullins', 'Munoz', 'Murillo',
            'Murphy', 'Murray', 'Myers', 'Nash', 'Navarro', 'Neal', 'Nelson', 'Newman',
            'Newton', 'Nguyen', 'Nichols', 'Nicholson', 'Nielsen', 'Nixon', 'Noble',
            'Nolan', 'Norman', 'Norris', 'Norton', 'Novak', 'Nunez', 'Obrien', 'Ochoa',
            'Oconnell', 'Oconnor', 'Odom', 'Odonnell', 'Olsen', 'Olson', 'Oneal',
            'Oneill', 'Orozco', 'Orr', 'Ortega', 'Ortiz', 'Osborn', 'Osborne', 'Owen',
            'Owens', 'Pace', 'Pacheco', 'Padilla', 'Page', 'Palmer', 'Park', 'Parker',
            'Parks', 'Parrish', 'Parsons', 'Patel', 'Patrick', 'Patterson', 'Patton',
            'Paul', 'Payne', 'Pearson', 'Peck', 'Pena', 'Pennington', 'Perez', 'Perkins',
            'Perry', 'Peters', 'Petersen', 'Peterson', 'Petty', 'Phelps', 'Phillips',
            'Pierce', 'Pineda', 'Pittman', 'Pitts', 'Pollard', 'Ponce', 'Poole',
            'Pope', 'Porter', 'Potter', 'Potts', 'Powell', 'Powers', 'Pratt', 'Preston',
            'Price', 'Prince', 'Proctor', 'Pruitt', 'Puckett', 'Pugh', 'Quinn',
            'Ramirez', 'Ramos', 'Ramsey', 'Randall', 'Randolph', 'Rangel', 'Rasmussen',
            'Ratliff', 'Ray', 'Raymond', 'Reed', 'Reese', 'Reeves', 'Reid', 'Reilly',
            'Reyes', 'Reynolds', 'Rhodes', 'Rice', 'Rich', 'Richard', 'Richards',
            'Richardson', 'Richmond', 'Riddle', 'Riggs', 'Riley', 'Rios', 'Ritter',
            'Rivas', 'Rivera', 'Rivers', 'Roach', 'Robbins', 'Roberson', 'Roberts',
            'Robertson', 'Robinson', 'Robles', 'Rocha', 'Rodgers', 'Rodriguez', 'Rogers',
            'Rojas', 'Rollins', 'Roman', 'Romero', 'Rosales', 'Rosario', 'Rose',
            'Ross', 'Roth', 'Rowe', 'Rowland', 'Roy', 'Rubio', 'Ruiz', 'Rush',
            'Russell', 'Russo', 'Ryan', 'Salas', 'Salazar', 'Salinas', 'Sampson',
            'Sanchez', 'Sanders', 'Sandoval', 'Sanford', 'Santana', 'Santiago',
            'Santos', 'Sargent', 'Saunders', 'Savage', 'Sawyer', 'Schaefer', 'Schmidt',
            'Schmitt', 'Schneider', 'Schroeder', 'Schultz', 'Schwartz', 'Scott',
            'Sellers', 'Serrano', 'Sexton', 'Shaffer', 'Shah', 'Shannon', 'Sharp',
            'Shaw', 'Shea', 'Shelton', 'Shepard', 'Shepherd', 'Sheppard', 'Sherman',
            'Shields', 'Short', 'Silva', 'Simmons', 'Simon', 'Simpson', 'Sims',
            'Sinclair', 'Singleton', 'Skinner', 'Slater', 'Sloan', 'Small', 'Smith',
            'Snow', 'Snyder', 'Solis', 'Solomon', 'Sosa', 'Soto', 'Sparks', 'Spears',
            'Spence', 'Spencer', 'Stafford', 'Stanley', 'Stanton', 'Stark', 'Steele',
            'Stein', 'Stephens', 'Stephenson', 'Stevens', 'Stevenson', 'Stewart',
            'Stokes', 'Stone', 'Stout', 'Strickland', 'Strong', 'Stuart', 'Suarez',
            'Sullivan', 'Summers', 'Sutton', 'Swanson', 'Sweeney', 'Swift', 'Tanner',
            'Tapia', 'Tate', 'Taylor', 'Terrell', 'Terry', 'Thomas', 'Thompson',
            'Thornton', 'Todd', 'Torres', 'Townsend', 'Tran', 'Travis', 'Trevino',
            'Trujillo', 'Tucker', 'Turner', 'Tyler', 'Underwood', 'Valdez', 'Valencia',
            'Valentine', 'Valenzuela', 'Vance', 'Vang', 'Vargas', 'Vasquez', 'Vaughan',
            'Vaughn', 'Vazquez', 'Vega', 'Velasquez', 'Velazquez', 'Velez', 'Villa',
            'Villanueva', 'Villarreal', 'Villegas', 'Vincent', 'Wade', 'Wagner',
            'Walker', 'Wall', 'Wallace', 'Waller', 'Walls', 'Walsh', 'Walter', 'Walters',
            'Walton', 'Wang', 'Ward', 'Ware', 'Warner', 'Warren', 'Washington', 'Waters',
            'Watkins', 'Watson', 'Watts', 'Weaver', 'Webb', 'Weber', 'Webster', 'Weeks',
            'Weiss', 'Welch', 'Wells', 'West', 'Wheeler', 'Whitaker', 'White', 'Whitehead',
            'Whitfield', 'Whitley', 'Whitney', 'Wiggins', 'Wilcox', 'Wiley', 'Wilkerson',
            'Wilkins', 'Wilkinson', 'Williams', 'Williamson', 'Willis', 'Wilson',
            'Winters', 'Wise', 'Witt', 'Wolf', 'Wolfe', 'Wong', 'Wood', 'Woodard',
            'Woods', 'Woodward', 'Wooten', 'Workman', 'Wright', 'Wu', 'Wyatt', 'Wynn',
            'Yang', 'Yates', 'Yoder', 'York', 'Young', 'Yu', 'Zamora', 'Zavala',
            'Zimmerman', 'Zuniga']

LIKE_LITERAL = '%ee%'
LIKE_VARIANTS = ['ee', 'ef', 'ee x', 'EE']

NAME_BOUNDARY = ['Brown', 'brown']

DUP_SHARE = (0.20, 0.50)


def _is_num(x) -> bool:
    if isinstance(x, bool):
        return False
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


def balance_band(rng) -> tuple:
    """Pick one of the three balance bands (small / medium / large)."""
    return BALANCE_BANDS[rng.randrange(len(BALANCE_BANDS))]


def draw_balance(rng) -> float:
    """Non-negative decimal amount from a random band (spec: FLOAT_balance)."""
    lo, hi = balance_band(rng)
    v = rng.uniform(lo, hi)
    return round(v, 2)


def name_variants(base: str, rng) -> list:
    """Near-duplicate variants of a surname (case, prefix/suffix, dropped char)."""
    out = [base, base.lower(), base.upper(), base + ' x', 'x ' + base]
    if len(base) > 2:
        i = rng.randrange(len(base))
        out.append(base[:i] + base[i + 1:])
    return out


def like_matches(name: str) -> bool:
    """Python-side LIKE '%ee%' (case-insensitive) for the near-variant rule."""
    return 'ee' in str(name).lower()
