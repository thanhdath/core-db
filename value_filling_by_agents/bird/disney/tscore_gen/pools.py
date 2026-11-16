"""Literal pools and value domains."""

MOVIE_TITLES = [
    "Aladdin", "Alice in Wonderland", "Atlantis: The Lost Empire", "Bambi",
    "Beauty and the Beast", "Big Hero 6", "Bolt", "Brother Bear",
    "101 Dalmatians", "102 Dalmatians", "1492: Conquest of Paradise",
    "20,000 Leagues Under the Sea", "25th Hour", "3 Men and a Baby",
    "3 Men and a Little Lady", "3 Ninjas", "Chicken Little",
    "The Aristocats", "The Return of Jafar", "The Hunchback of Notre Dame",
    "The Little Mermaid", "Wreck-It Ralph", "Pinocchio", "Dumbo",
    "Cinderella", "Snow White and the Seven Dwarfs", "The Jungle Book",
    "Robin Hood", "The Great Mouse Detective", "Sleeping Beauty",
    "Peter Pan", "Lady and the Tramp", "One Hundred and One Dalmatians",
    "The Sword in the Stone", "Mary Poppins", "The Fox and the Hound",
    "The Black Cauldron", "The Rescuers", "The Rescuers Down Under",
    "Pocahontas", "Mulan", "Tarzan", "Fantasia", "Saludos Amigos",
    "The Three Caballeros", "Make Mine Music", "Fun and Fancy Free",
    "Melody Time", "The Adventures of Ichabod and Mr. Toad",
]

HEROES = [
    "Snow White", "Pinocchio", "Dumbo", "Bambi", "Donald Duck",
    "Mickey Mouse", "Mr. Toad and Ichabod Crane", "Cinderella",
    "Aladdin", "Abu", "Ariel", "Belle", "Beast", "Simba", "Mulan",
    "Tarzan", "Robin Hood", "Peter Pan", "Winnie the Pooh", "Stitch",
    "Woody", "Buzz Lightyear", "Nemo", "Ralph", "Elsa", "Anna",
    "Moana", "Maui", "Hercules", "Quasimodo", "Pocahontas", "Tiana",
]

VILLAINS = [
    "Evil Queen", "Stromboli", "Chernabog", "Ringmaster", "Hunter",
    "Willie the Giant", "Mr. Winkie and The Headless Horseman",
    "Lady Tremaine", "Jafar", "Ursula", "Gaston", "Scar", "Hades",
    "Maleficent", "Captain Hook", "Cruella de Vil", "Shere Khan",
    "Commander Rourke", "Ratigan", "Prince John", "Shan Yu",
    "Clayton", "Oogie Boogie", "Syndrome", "Mother Gothel",
]

SONGS = [
    "Some Day My Prince Will Come", "When You Wish upon a Star",
    "Baby Mine", "Love Is a Song", "Saludos Amigos",
    "Little Toot", "The Merrily Song", "Bibbidi-Bobbidi-Boo",
    "A Whole New World", "Beauty and the Beast", "Circle of Life",
    "Under the Sea", "Part of Your World", "Let It Go", "How Far I'll Go",
    "Colors of the Wind", "You've Got a Friend in Me", "Little Wonders",
    "Hakuna Matata", "Can You Feel the Love Tonight", "Reflection",
    "Go the Distance", "Once Upon a Dream", "When She Loved Me",
]

DIRECTORS = [
    "David Hand", "Ben Sharpsteen", "Jack Kinney", "Norman Ferguson",
    "Clyde Geronimi", "Wilfred Jackson", "Hamilton Luske",
    "Wolfgang Reitherman", "John Lasseter", "Brad Bird", "Andrew Stanton",
    "Chris Buck", "Jennifer Lee", "Ron Clements", "John Musker",
    "Gary Trousdale", "Kirk Wise", "Roger Allers", "Rob Minkoff",
    "Byron Howard", "Rich Moore", "Nathan Greno", "Chris Williams",
    "Don Hall", "Chris Buck and Jennifer Lee", "full credits",
]

VOICE_ACTORS = [
    "Joan Cusack", "Monica Evans", "Jason Alexander", "Frank Welker",
    "None", "Sherry Lynn", "Greg Germann", "Kevin McDonald",
    "Scott Weinger", "Robin Williams", "Jodi Benson", "Paige O'Hara",
    "Robby Benson", "Jonathan Taylor Thomas", "Matthew Broderick",
    "Ming-Na Wen", "Tom Hulce", "Demi Moore", "Lea Salonga",
    "Idina Menzel", "Kristen Bell", "Auli'i Cravalho", "Dwayne Johnson",
    "Tom Hanks", "Tim Allen", "Ellen DeGeneres", "John C. Reilly",
    "Sarah Silverman", "James Earl Jones", "Jeremy Irons",
]

CHARACTERS = [
    "Abby Mallard", "Abigail Gabble", "Abis Mal", "Abu", "Achilles",
    "Adella", "Adorabeezle Winterpop", "Agent Wendy Pleakley",
    "Aladdin", "Ariel", "Belle", "Beast", "Simba", "Mulan", "Tarzan",
    "Robin Hood", "Peter Pan", "Winnie the Pooh", "Stitch", "Woody",
    "Buzz Lightyear", "Nemo", "Ralph", "Elsa", "Anna", "Moana", "Maui",
    "Hercules", "Quasimodo", "Pocahontas", "Tiana", "Jafar", "Ursula",
    "Gaston", "Scar", "Hades", "Maleficent", "Captain Hook",
    "Cruella de Vil", "Shere Khan", "Commander Rourke", "Ratigan",
]

GENRES = [
    "Musical", "Adventure", "Drama", "Comedy", "Action", "Horror",
    "Romantic Comedy", "", "Family", "Animation", "Sci-Fi", "Fantasy",
    "Thriller", "Documentary",
]

MPAA_RATINGS = ["G", "PG", "PG-13", "R", "Not Rated", ""]

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

REVENUE_YEARS = list(range(1991, 2017))

STUDIO_ENT_RANGE = (2000.0, 8000.0)
CONSUMER_PROD_RANGE = (500.0, 4000.0)
INTERACTIVE_RANGE = (100, 1200)
PARKS_RANGE = (2500.0, 6000.0)
MEDIA_NETWORKS_RANGE = (300.0, 10000.0)
TOTAL_RANGE = (5000, 25000)

TOTAL_GROSS_RANGE = (1_000_000, 1_000_000_000)
INFLATION_GROSS_RANGE = (10_000_000, 6_000_000_000)

TOTAL_GROSS_BOUNDARY = [99999999, 100000000, 100000001]
RELEASE_YEAR_BOUNDARY = [1936, 1937, 1938, 1989, 1990, 1991]
CHAR_YEAR_BOUNDARY = [36, 37, 38, 49, 50, 51]
REVENUE_YEAR_BOUNDARY = [1996, 1997, 1998, 1999]

RELEASE_LIKE_VARIANTS = [
    "Dec 1, 1990", "Ded 1, 1990", "Dec x 1, 1990", "dec 1, 1990",
    "Mar 30, 2008", "Mar 30, 2007x", "mar 30, 2007",
    "Jan 1, 1977", "Apr 1, 1970", "Jun 1, 2016",
]

TITLE_BOUNDARY = ["Alice in Wonderland", "alice in wonderland",
                  "Pinocchio", "pinocchio", "Bambi", "bambi"]
VILLAIN_BOUNDARY = ["Alice in Wonderland", "alice in wonderland",
                    "Commander Rourke", "commander rourke"]
DIRECTOR_NAME_BOUNDARY = ["Pinocchio", "pinocchio",
                          "Wreck-It Ralph", "wreck-it ralph"]
GROSS_TITLE_BOUNDARY = ["Beauty and the Beast", "beauty and the beast",
                        "Wreck-It Ralph", "wreck-it ralph",
                        "The Great Mouse Detective", "the great mouse detective"]

TABLE_SIZES = {
    "voice-actors": 200,
    "characters": 56,
    "director": 56,
    "movies_total_gross": 200,
    "revenue": 26,
}

TIE_TOTAL_MIN = TOTAL_GROSS_RANGE[0]
TIE_TOTAL_MAX = TOTAL_GROSS_RANGE[1]
TIE_INFL_MAX = INFLATION_GROSS_RANGE[1]
