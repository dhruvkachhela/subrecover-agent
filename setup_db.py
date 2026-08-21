# How this works:
# Setup script that creates the database tables and populates them
# with the generated synthetic failed subscription CSV dataset.

from app.database import init_db, load_csv_to_db

if __name__ == "__main__":
    init_db()
    load_csv_to_db()
