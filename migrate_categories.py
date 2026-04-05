"""
One-time migration: assign categories to existing equipment and food items
that were seeded before the category column was added.
"""
import sqlite3, os

DB = os.path.join(os.path.dirname(__file__), "jimnycamp.db")

EQUIP_MAP = {
    "Σκήνη (Tent)": "Διαμονή & Ύπνος",
    "Στρώμα αέρος / Στρώμα": "Διαμονή & Ύπνος",
    "Υπνοσάκκο": "Διαμονή & Ύπνος",
    "Μαξιλάρι ορθοπεδικό": "Διαμονή & Ύπνος",
    "Ground cloth/tarp": "Διαμονή & Ύπνος",
    "Mat for tent entrance": "Διαμονή & Ύπνος",
    "Hammock": "Διαμονή & Ύπνος",
    "Καρέκλες πτυσσόμενες": "Έπιπλα & Φωτισμός",
    "Τραπέζι πτυσσόμενο": "Έπιπλα & Φωτισμός",
    "Λάμπα μπαταρίας": "Έπιπλα & Φωτισμός",
    "Φωτισμός": "Έπιπλα & Φωτισμός",
    "Σπίρτα / Αναπτήρα": "Έπιπλα & Φωτισμός",
    "Γκάζι για ψήσιμο / BBQ & Stove": "Κουζίνα & Εργαλεία",
    "Τηγάνι + παρελκόμενα": "Κουζίνα & Εργαλεία",
    "Παγωνιέρα": "Κουζίνα & Εργαλεία",
    "Σανίδι κοπής": "Κουζίνα & Εργαλεία",
    "Μαχαίρι του σεφ": "Κουζίνα & Εργαλεία",
    "Πιάτα / Ποτήρια / Μαχαιροπίρουνα": "Κουζίνα & Εργαλεία",
    "Παγούρι νερό / Water Tank / Θέρμος": "Κουζίνα & Εργαλεία",
    "Υγρό πιάτων και σφουγγαράκι": "Κουζίνα & Εργαλεία",
    "Υγρό χεριών / Σαπούνι": "Κουζίνα & Εργαλεία",
    "Εργαλειοθήκη": "Κουζίνα & Εργαλεία",
    "Πυροσβεστήρα": "Κουζίνα & Εργαλεία",
    "Dust pan/brush": "Κουζίνα & Εργαλεία",
    "Drone": "Τεχνολογία",
    "GoPro / Camera gear": "Τεχνολογία",
    "Bluetooth μεγάφωνο / Music": "Τεχνολογία",
    "Power banks": "Τεχνολογία",
    "Καλώδιο extension": "Τεχνολογία",
}

FOOD_MAP = {
    "Ελαιόλαδο / Αλάτι / Πιπέρι / Ρίγανη / Πάπρικα": "Προμήθειες",
    "Καφέ / Ζάχαρη / Τσάι / Εσπρεσιέρα": "Προμήθειες",
    "Ρύζι": "Προμήθειες",
    "Κονσέρβα / Corn beef": "Προμήθειες",
    "Ψωμί κουλούρι (φέττες)": "Προμήθειες",
    "Αυγά (18)": "Προμήθειες",
    "Χαλλούμια": "Προμήθειες",
    "Λουκάνικα": "Προμήθειες",
    "Λούντζα": "Προμήθειες",
    "Ντοματίνια / Αγγουράκια / Καρότο": "Φρέσκα & Σνακ",
    "Chips": "Φρέσκα & Σνακ",
    "Νερό (πόσιμο)": "Ποτά",
    "Μπύρες (Corona / Fix)": "Ποτά",
    "Αναψυκτικά (Coke, 7up, κλπ)": "Ποτά",
    "Πάγο": "Ποτά",
    "Χρυσό Ρινόκερο": "Άλλα",
    "Πράσινο Ρινόκερο": "Άλλα",
    "Mosquito repellent": "Άλλα",
    "Αντηλιακό / Αποσμητικό": "Άλλα",
    "Hiking Shoes": "Άλλα",
}


def run():
    db = sqlite3.connect(DB)
    equip_updated = 0
    food_updated = 0

    # Exact-text match (for items added by seed)
    for text, cat in EQUIP_MAP.items():
        cur = db.execute(
            "UPDATE equipment_item SET category=? WHERE text=? AND (category='' OR category IS NULL)",
            (cat, text),
        )
        equip_updated += cur.rowcount
    for text, cat in FOOD_MAP.items():
        cur = db.execute(
            "UPDATE food_item SET category=? WHERE text=? AND (category='' OR category IS NULL)",
            (cat, text),
        )
        food_updated += cur.rowcount

    # Fuzzy keyword match for manually-entered variant texts
    EQUIP_KEYWORD_RULES = [
        ("Σκηνή",                        "Διαμονή & Ύπνος"),
        ("Στρώμα",                        "Διαμονή & Ύπνος"),
        ("Υπνόσακκος",                    "Διαμονή & Ύπνος"),
        ("Ωτοασπίδες",                    "Διαμονή & Ύπνος"),
        ("Γκάζι",                         "Κουζίνα & Εργαλεία"),
        ("Κουζίνα",                       "Κουζίνα & Εργαλεία"),
        ("Εσπρεσιέρα",                    "Κουζίνα & Εργαλεία"),
        ("Παγούρι",                       "Κουζίνα & Εργαλεία"),
        ("Υγρό χεριών",                   "Κουζίνα & Εργαλεία"),
        ("Καρέκλες",                      "Έπιπλα & Φωτισμός"),
        ("Καλώδιο",                       "Τεχνολογία"),
        ("GoPro",                         "Τεχνολογία"),
        ("Bluetooth",                     "Τεχνολογία"),
        ("Ρινόκερο",                      "Άλλα"),
    ]
    FOOD_KEYWORD_RULES = [
        ("Καφέ",                          "Προμήθειες"),
        ("Corn beef",                     "Προμήθειες"),
        ("Κολοκυθάκια",                   "Φρέσκα & Σνακ"),
        ("Ντοματίνια",                    "Φρέσκα & Σνακ"),
        ("Ψωμί",                          "Προμήθειες"),
        ("Μπύρες",                        "Ποτά"),
        ("Πάγος",                         "Ποτά"),
        ("Αναψυκτικά",                    "Ποτά"),
        ("Sieftalia",                     "Προμήθειες"),
    ]

    for keyword, cat in EQUIP_KEYWORD_RULES:
        cur = db.execute(
            "UPDATE equipment_item SET category=? WHERE text LIKE ? AND (category='' OR category IS NULL)",
            (cat, f"%{keyword}%"),
        )
        equip_updated += cur.rowcount
    for keyword, cat in FOOD_KEYWORD_RULES:
        cur = db.execute(
            "UPDATE food_item SET category=? WHERE text LIKE ? AND (category='' OR category IS NULL)",
            (cat, f"%{keyword}%"),
        )
        food_updated += cur.rowcount

    db.commit()
    print(f"Equipment rows updated: {equip_updated}")
    print(f"Food rows updated: {food_updated}")

    # Verify
    print("\nEquipment by category:")
    for row in db.execute("SELECT category, count(*) FROM equipment_item GROUP BY category ORDER BY category").fetchall():
        print(f"  {row[0] or '(none)'}: {row[1]}")
    print("\nFood by category:")
    for row in db.execute("SELECT category, count(*) FROM food_item GROUP BY category ORDER BY category").fetchall():
        print(f"  {row[0] or '(none)'}: {row[1]}")
    db.close()


if __name__ == "__main__":
    run()
