"""Rebuild the dedicated tertiary-A database from the current directory."""

from app.hospital_store import database_path
from app.tertiary_store import build_tertiary_database, tertiary_database_path


if __name__ == '__main__':
    print(build_tertiary_database(database_path(), tertiary_database_path()))
