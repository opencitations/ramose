import csv
import io
import json


def to_nested(csv_string, request_url="", base_url=""):
    rows = list(csv.DictReader(io.StringIO(csv_string)))
    articles = {}
    for row in rows:
        article = articles.setdefault(row["br"], {"identifier": row["doi"], "omid": row["br"], "references": []})
        article["references"].append(row["cited"])
    return json.dumps(list(articles.values()), indent=2)
