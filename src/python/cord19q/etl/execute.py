"""
Transforms raw CORD-19 data into an articles.db sqlite database.
"""

import csv
import hashlib
import json
import os.path
import re
import sqlite3
import sys

import dateutil.parser as parser

# Articles schema
ARTICLES = {
    'Id': 'TEXT PRIMARY KEY',
    'Source': 'TEXT',
    'Published': 'DATETIME',
    'Publication': "TEXT",
    'Authors': 'TEXT',
    'Title': 'TEXT',
    'Tags': 'TEXT',
    'Reference': 'TEXT'
}

# Sections schema
SECTIONS = {
    'Id': 'INTEGER PRIMARY KEY',
    'Article': 'TEXT',
    'Text': 'TEXT',
    'Tags': 'TEXT'
}

# SQL statements
CREATE_TABLE = "CREATE TABLE IF NOT EXISTS {table} ({fields})"
INSERT_ROW = "INSERT INTO {table} ({columns}) VALUES ({values})"

def create(db, table, name):
    """
    Creates a SQLite table.

    Args:
        db: database connection
        table: table schema
        name: table name
    """

    columns = ['{0} {1}'.format(name, ctype) for name, ctype in table.items()]
    create = CREATE_TABLE.format(table=name, fields=", ".join(columns))

    # pylint: disable=W0703
    try:
        db.execute(create)
    except Exception as e:
        print(create)
        print("Failed to create table: " + e)

def insert(db, table, name, row):
    """
    Builds and inserts an article.

    Args:
        db: article database
        table: table object
        name: table name
        row: row to insert
    """

    # Build insert prepared statement
    columns = [name for name, _ in table.items()]
    insert = INSERT_ROW.format(table=name,
                               columns=", ".join(columns),
                               values=("?, " * len(columns))[:-2])

    try:
        # Execute insert statement
        db.execute(insert, values(table, row, columns))
    # pylint: disable=W0703
    except Exception as ex:
        print("Error inserting row: {}".format(row[0]), ex)

def values(table, row, columns):
    """
    Formats and converts row into database types based on table schema.

    Args:
        table: table schema
        row: row tuple
        columns: column names

    Returns:
        Database schema formatted row tuple
    """

    values = []
    for x, column in enumerate(columns):
        # Get value
        value = row[x]

        if table[column].startswith('INTEGER'):
            values.append(int(value) if value else 0)
        elif table[column] == 'BOOLEAN':
            values.append(1 if value == "TRUE" else 0)
        else:
            values.append(value)

    return values

def getId(row):
    """
    Gets a row id. Builds one from the title if no body content is available.

    Args:
        row: input row

    Returns:
        row id as a sha1 hash
    """

    # Use sha1 provided, if available
    uid = row["sha"]
    if not uid:
        # Fallback to sha1 of title
        uid = hashlib.sha1(row["title"].encode("utf-8")).hexdigest()

    return uid

def getDate(row):
    """
    Parses the publish date from the input row.

    Args:
        row: input row

    Returns:
        publish date
    """

    date = row["publish_time"]

    if date:
        try:
            if date.isdigit() and len(date) == 4:
                # Default entries with just year to Jan 1
                date += "-01-01"

            return parser.parse(date)

        # pylint: disable=W0702
        except:
            # Skip parsing errors
            return None

    return None

def getAuthors(row):
    """
    Parses an authors string from the input row.

    Args:
        row: input row

    Returns:
        authors string
    """

    authors = row["authors"]

    if authors and "[" in authors:
        # Attempt to parse list string
        authors = "; ".join(re.findall(r"'\s*([^']*?)\s*'", authors))

    return authors

def getTags(sections):
    """
    Searches input sections for matching keywords. If found, returns the keyword tag.

    Args:
        sections: list of text sections

    Returns:
        tags
    """

    keywords = ["2019-ncov", "covid-19", "sars-cov-2"]

    tags = None
    for text in sections:
        if any(x in text.lower() for x in keywords):
            tags = "COVID-19"

    return tags

def getReference(row):
    """
    Builds a reference link.

    Args:
        row: input row

    Returns:
        resolved reference link
    """

    # Resolve doi link
    text = row["doi"]

    if text and not text.startswith("http") and not text.startswith("doi.org"):
        return "https://doi.org/" + text

    return text

def read(directory, uid):
    """
    Reads body text for a given row id. Body text is returned as a list of sections.

    Args:
        directory: input directory
        uid: row id

    Returns:
        list of sections
    """

    sections = []

    if uid:
        # Build article path
        article = os.path.join(directory, "articles", uid + ".json")

        if os.path.exists(article):
            with open(article) as jfile:
                data = json.load(jfile)

                # Extract text from each section
                sections = [row["text"] for row in data["body_text"]]

    return sections

def run():
    """
    Main execution method.
    """

    # Read input directory path
    directory = sys.argv[1]

    print("Building articles.db from {}".format(directory))

    # Output directory - create if it doesn't exist
    output = os.path.join(os.path.expanduser("~"), ".cord19", "models")
    os.makedirs(output, exist_ok=True)

    # Output database file
    dbfile = os.path.join(output, "articles.db")

    # Delete existing file
    if os.path.exists(dbfile):
        os.remove(dbfile)

    # Create output database
    db = sqlite3.connect(dbfile)

    # Create articles table
    create(db, ARTICLES, "articles")

    # Create sections table
    create(db, SECTIONS, "sections")

    # Row index
    index = 0
    sid = 0

    with open(os.path.join(directory, "metadata.csv"), mode="r") as csvfile:
        for row in csv.DictReader(csvfile):
            # Generate uid
            uid = getId(row)

            # Published date
            date = getDate(row)

            # Get text sections
            sections = [row["title"]] + read(directory, uid)

            # Get tags
            tags = getTags(sections)

            # Article row
            # id, source, published, publication, authors, title, tags, reference
            article = (uid, row["source_x"], date, row["journal"], getAuthors(row), row["title"], tags, getReference(row))
            insert(db, ARTICLES, "articles", article)

            # Increment number of articles processed
            index += 1
            if index % 1000 == 0:
                print("Inserted {} articles".format(index))

            # Add each text section
            for text in sections:
                # id, article, text, tags
                insert(db, SECTIONS, "sections", (sid, uid, text, tags))
                sid += 1

    print("Total rows inserted: {}".format(index))

    # Commit changes and close
    db.commit()
    db.close()

if __name__ == "__main__":
    run()
