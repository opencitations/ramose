# SPDX-FileCopyrightText: 2018-2021 Silvio Peroni <silvio.peroni@unibo.it>
# SPDX-FileCopyrightText: 2020-2021 Marilena Daquino <marilena.daquino2@unibo.it>
# SPDX-FileCopyrightText: 2022 Davide Brembilla
# SPDX-FileCopyrightText: 2024 Ivan Heibi <ivan.heibi2@unibo.it>
# SPDX-FileCopyrightText: 2025 Sergei Slinkin
# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from datetime import datetime
from sys import maxsize

from dateutil.parser import parse
from isodate import parse_duration


class DataType(object):
    def __init__(self):
        """This class implements all the possible data types that can be used within
        the configuration file of RAMOSE. In particular, it provides methods for converting
        a string into the related Python data type representation."""
        self.func = {
            "str": DataType.str,
            "int": DataType.int,
            "float": DataType.float,
            "duration": DataType.duration,
            "datetime": DataType.datetime
        }

    def get_func(self, name_str: str):
        """This method returns the method for handling a given data type expressed as a string name."""
        return self.func[name_str]

    @staticmethod
    def duration(s):
        """This method returns the data type for durations according to the XML Schema
        Recommendation (https://www.w3.org/TR/xmlschema11-2/#duration) from the input string.
        In case the input string is None or it is empty, an high duration value
        (i.e. 2000 years) is returned."""
        if s is None or s == "":
            d = parse_duration("P2000Y")
        else:
            d = parse_duration(s)

        return datetime(1983, 1, 15) + d

    @staticmethod
    def datetime(s):
        """This method returns the data type for datetime according to the ISO 8601
           (https://en.wikipedia.org/wiki/ISO_8601) from the input string. In case the input string is None or
           it is empty, a low date value (i.e. 0001-01-01) is returned."""
        default = datetime(1, 1, 1, 0, 0)
        if s is None or s == "":
            d = parse("0001-01-01", default=default)
        else:
            d = parse(s, default=default)

        return d

    @staticmethod
    def str(s):
        """This method returns the data type for strings. In case the input string is None, an empty string
        is returned."""
        if s is None:
            l = ""
        else:
            l = str(s).lower()

        return l

    @staticmethod
    def int(s):
        """This method returns the data type for integer numbers from the input string. In case the input string is
        None or it is empty, a low integer value is returned."""
        if s is None or s == "":
            i = -maxsize
        else:
            i = int(s)

        return i

    @staticmethod
    def float(s):
        """This method returns the data type for float numbers from the input string. In case the input string is
            None or it is empty, a low float value is returned."""
        if s is None or s == "":
            f = float(-maxsize)
        else:
            f = float(s)

        return f
