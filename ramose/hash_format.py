# SPDX-FileCopyrightText: 2018-2021 Silvio Peroni <silvio.peroni@unibo.it>
# SPDX-FileCopyrightText: 2020-2021 Marilena Daquino <marilena.daquino2@unibo.it>
# SPDX-FileCopyrightText: 2022 Davide Brembilla
# SPDX-FileCopyrightText: 2024 Ivan Heibi <ivan.heibi2@unibo.it>
# SPDX-FileCopyrightText: 2025 Sergei Slinkin
# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from pathlib import Path
from re import DOTALL, search


def parse_custom_params(raw: str) -> dict[str, dict[str, str]]:
    result = {}
    for raw_part in raw.split(";"):
        part = raw_part.strip()
        if not part:
            continue
        name, handler, phase, *desc_parts = part.split(",", 3)
        result[name.strip()] = {
            "handler": handler.strip(),
            "phase": phase.strip(),
            "description": desc_parts[0].strip() if desc_parts else "",
        }
    return result


class HashFormatHandler:
    """This class creates an object capable to read files stored in Hash Format (see
    https://github.com/opencitations/ramose#Hashformat-configuration-file). A Hash Format
    file (.hf) is a specification file that includes information structured using the following
    syntax:

    ```
    #<field_name_1> <field_value_1>
    #<field_name_1> <field_value_2>
    #<field_name_3> <field_value_3>
    [...]
    #<field_name_n> <field_value_n>
    ```"""

    def read(self, file_path):
        """This method takes in input a path of a file containing a document specified in
        Hash Format, and returns its representation as list of dictionaries."""
        result = []

        with Path(file_path).open(newline=None) as f:
            first_field_name = None
            cur_object: dict[str, str] = {}
            cur_field_name = None
            for line in f:
                cur_matching = search(r"^#([^\s]+)\s(.+)$", line, DOTALL)
                if cur_matching is not None:
                    cur_field_name = cur_matching.group(1)
                    cur_field_content = cur_matching.group(2)

                    # If both the name and the content are defined, continue to process
                    if cur_field_name and cur_field_content:
                        # Identify the separator key
                        if first_field_name is None:
                            first_field_name = cur_field_name

                        # If the current field is equal to the separator key,
                        # then create a new object
                        if cur_field_name == first_field_name:
                            # If there is an already defined object, add it to the
                            # final result
                            if cur_object:
                                result.append(cur_object)
                            cur_object = {}

                        # Add the new key to the object
                        cur_object[cur_field_name] = cur_field_content
                elif cur_object and cur_field_name is not None:
                    cur_object[cur_field_name] += line

            if cur_object:
                result.append(cur_object)

        # Clean the final \n
        for item in result:
            for key in item:
                item[key] = item[key].rstrip()

        return result
