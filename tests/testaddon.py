# SPDX-FileCopyrightText: 2026 Sergei Slinkin
#
# SPDX-License-Identifier: ISC

import csv
import io
import xml.etree.ElementTree as ET
import re

def lower(s):
    return s.lower(),


def split_dois(s):
    return "\"%s\"" % "\" \"".join(s.split("__")),

def to_upper(csv_str):
    """Dummy example: convert entire CSV to uppercase."""
    return csv_str.upper()

def to_dummyxml(csv_str):
    """Dummy: wrap CSV in <xml> tags."""
    return f"<xml>\n{csv_str}\n</xml>"

def to_xml(csv_str):
    """
    Convert a CSV document (given as a string) into an XML document string.

    - Wraps all rows in a <records> root element.
    - Each row becomes a <record> element.
    - Each header becomes a child tag under <record>, with its cell text.
    - Invalid XML tag characters in headers are replaced with underscores.
    - Adds an XML declaration at the top.
    """
    # Helper: make a valid XML tag name from a header
    def _safe_tag(tag: str) -> str:
        # replace any character not letter, digit, underscore, hyphen, or period with underscore
        tag = re.sub(r'[^\w\-.]', '_', tag)
        # ensure it doesn't start with digit or punctuation
        if re.match(r'^[^A-Za-z_]', tag):
            tag = '_' + tag
        return tag

    # Parse CSV
    reader = csv.DictReader(io.StringIO(csv_str))
    headers = reader.fieldnames or []

    # Build XML tree
    root = ET.Element('records')
    for row in reader:
        rec = ET.SubElement(root, 'record')
        for h in headers:
            # create child even if empty
            child = ET.SubElement(rec, _safe_tag(h))
            val = row.get(h, '').strip()
            if val:
                child.text = val

    # Pretty‐print indentation
    def _indent(elem, level=0):
        i = "\n" + level*"  "
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "  "
            for c in elem:
                _indent(c, level+1)
            last = elem[-1]
            if not last.tail or not last.tail.strip():
                last.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i

    _indent(root)

    # Serialize to string with declaration
    xml_body = ET.tostring(root, encoding='unicode')
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_body

