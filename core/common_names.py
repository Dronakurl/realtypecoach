"""Embedded list of common names for exclusion from word statistics."""

# Common names sourced from public domain data:
# - English: US Census data (public domain)
# - German: German name statistics (common names, public domain sources)

COMMON_NAMES: dict[str, set[str]] = {
    "en": {
        # Top English first names
        "james", "john", "robert", "michael", "william", "david", "richard", "joseph",
        "thomas", "charles", "christopher", "daniel", "matthew", "anthony", "donald",
        "mark", "paul", "steven", "andrew", "kenneth", "joshua", "kevin", "brian",
        "george", "edward", "ronald", "timothy", "jason", "jeffrey", "ryan", "jacob",
        "gary", "nicholas", "eric", "jonathan", "stephen", "larry", "justin", "scott",
        "brandon", "benjamin", "samuel", "raymond", "gregory", "frank", "alexander",
        "patrick", "jack", "dennis", "jerry", "tyler", "aaron", "jose", "adam",
        "henry", "nathan", "douglas", "zachary", "peter", "kyle", "walter", "ethan",
        "joe", "harold", "randy", "lawrence", "mary", "patricia", "jennifer", "linda",
        "barbara", "elizabeth", "susan", "jessica", "sarah", "karen", "nancy", "lisa",
        "betty", "margaret", "sandra", "ashley", "kimberly", "emily", "donna", "michelle",
        "dorothy", "carol", "amanda", "melissa", "deborah", "stephanie", "rebecca",
        "sharon", "laura", "cynthia", "kathleen", "amy", "shirley", "angela", "helen",
        "anna", "brenda", "pamela", "nicole", "emma", "samantha", "katherine", "christine",
        "debra", "rachel", "catherine", "carolyn", "janet", "ruth", "maria", "heather",
        # Common English surnames
        "smith", "johnson", "williams", "brown", "jones", "garcia", "miller", "davis",
        "rodriguez", "martinez", "hernandez", "lopez", "gonzalez", "wilson", "anderson",
        "thomas", "taylor", "moore", "jackson", "martin", "lee", "perez", "thompson",
        "white", "harris", "sanchez", "clark", "ramirez", "lewis", "robinson", "walker",
        "young", "allen", "king", "wright", "scott", "torres", "nguyen", "hill", "flores",
        "green", "adams", "nelson", "baker", "hall", "rivera", "campbell", "mitchell",
        "carter", "roberts", "gomez", "phillips", "evans", "turner", "diaz", "parker",
        "cruz", "edwards", "collins", "reyes", "stewart", "morris", "morales", "murphy",
        "cook", "rogers", "gutierrez", "ortiz", "morgan", "cooper", "peters", "bailey",
        "reed", "kelly", "howard", "rivera", "cook", "rogers", "morgan", "peterson",
        "cooper", "reed", "bailey", "bell", "gomez", "kelly", "howard", "cox", "ward",
        "richardson", "watson", "brooks", "chavez", "wood", "bennett", "gray", "mendoza",
        "ruiz", "hughes", "price", "alvarez", "castillo", "sanders", "patel", "myers",
        "long", "ross", "foster", "jimenez", "powell",
    },
    "de": {
        # Common German first names
        "hans", "peter", "michael", "jürgen", "klaus", "wolfgang", "thomas", "andreas",
        "josef", "stefan", "werner", "manfred", "franz", "horst", "gerhard", "karl",
        "dieter", "helmut", "heinz", "roland", "martin", "bernd", "jochen", "friedrich",
        "wilhelm", "otto", "georg", "heinrich", "günter", "erich", "joachim", "rainer",
        "reinhard", "kurt", "horst", "alfred", "walter", "gustav", "hermann", "ernst",
        "rüdiger", "axel", "matthias", "torsten", "rene", "markus", "alexander", "daniel",
        "christian", "marvin", "maximilian", "felix", "luca", "paul", "jonas", "leon",
        "finn", "elias", "philipp", "lukas", "julian", "nico", "tim", "jan", "maria",
        "anna", "barbara", "elisabeth", "monika", "ursula", "gabriele", "petra", "sabine",
        "christiane", "susan", "sandra", "birgit", "stefanie", "andrea", "jutta", "karin",
        "renate", "helga", "brigitte", "marianne", "ilse", "ruth", "edith", "margarete",
        "hilde", "gertrud", "emma", "mia", "sophia", "hanna", "sofia", "leah", "lotte",
        "lina", "julia", "laura", "clara", "elara", "maya", "ava", "lena", "mathilda",
        # Common German surnames
        "müller", "schmidt", "schneider", "fischer", "weber", "meyer", "wagner", "becker",
        "schulz", "hoffmann", "koch", "richter", "klein", "wolf", "schröder", "neumann",
        "schwarz", "braun", "zimmermann", "krüger", "lange", "schubert", "müller",
        "miller", "schmid", "schmitt", "schulze", "schneider", "fischer", "weber", "becker",
        "wagner", "hoffmann", "koch", "bauer", "richter", "klein", "wolf", "schröder",
        "neumann", "schwarz", "braun", "zimmermann", "krüger", "lange", "schubert",
        "martin", "schultz", "lehmann", "jung", "hahn", "schmid", "schmitt", "schulze",
        "peters", "albert", "beck", "stein", "kaiser", "franz", "könig", "kraft",
        "huber", "bergmann", "hormann", "hormann", "fink", "burg", "dietrich", "busch",
        "berger", "kramer", "franke", "vogel", "jager", "lange", "pohl", "ernst",
        "berg", "thomas", "roth", "gross", "hein", "friend", "friedrich", "winkler",
        "keller", "gottschalk", "voigt", "schuster", "kramer", "binder", "preuss",
    },
}

__all__ = ["COMMON_NAMES"]
