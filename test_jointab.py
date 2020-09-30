import unittest
from dataclasses import dataclass
from typing import Dict, Optional
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
from jointab import migrate_params, render
from cjwmodule.testing.i18n import i18n_message


@dataclass(frozen=True)
class RenderColumn:
    """
    Column presented to a render() function in its `input_columns` argument.

    A column has a `name` and a `type`. The `type` is one of "number", "text"
    or "timestamp".
    """

    name: str
    """Column name in the DataFrame."""

    type: str
    """'number', 'text' or 'timestamp'."""

    format: Optional[str]
    """
    Format string for converting the given column to string.

    >>> column = RenderColumn('A', 'number', '{:,d} bottles of beer')
    >>> column.format.format(1234)
    '1,234 bottles of beer'
    """


@dataclass(frozen=True)
class TabOutput:
    """
    Tab data presented to a render() function.

    A tab has `slug` (JS-side ID), `name` (user-assigned tab name), `dataframe`
    (pandas.DataFrame), and `columns` (dict of `RenderColumn`, keyed by each
    column in `dataframe.columns`.)

    `columns` is designed to mirror the `input_columns` argument to render().
    It's a Dict[str, RenderColumn].
    """

    slug: str
    """
    Tab slug (permanent ID, unique in this Workflow, that leaks to the user).
    """

    name: str
    """Tab name visible to the user and editable by the user."""

    columns: Dict[str, RenderColumn]
    """
    Columns output by the final module in this tab.

    `set(columns.keys()) == set(dataframe.columns)`.
    """

    dataframe: pd.DataFrame
    """
    DataFrame output by the final module in this tab.
    """


class MigrateTests(unittest.TestCase):
    def test_v0(self):
        self.assertEqual(
            migrate_params(
                {
                    "right_tab": "tab-1",
                    "join_columns": {"on": "A,B", "right": "C,D"},
                    "type": 0,
                }
            ),
            {
                "right_tab": "tab-1",
                "join_columns": {"on": ["A", "B"], "right": ["C", "D"]},
                "type": "left",
            },
        )

    def test_v0_empty_multicolumns(self):
        self.assertEqual(
            migrate_params(
                {
                    "right_tab": "tab-1",
                    "join_columns": {"on": "", "right": ""},
                    "type": 0,
                }
            ),
            {
                "right_tab": "tab-1",
                "join_columns": {"on": [], "right": []},
                "type": "left",
            },
        )

    def test_v1(self):
        self.assertEqual(
            migrate_params(
                {
                    "right_tab": "tab-1",
                    "join_columns": {"on": ["A", "B"], "right": ["C", "D"]},
                    "type": "inner",
                }
            ),
            {
                "right_tab": "tab-1",
                "join_columns": {"on": ["A", "B"], "right": ["C", "D"]},
                "type": "inner",
            },
        )


class JoinTabTests(unittest.TestCase):
    def test_left(self):
        left = pd.DataFrame({"A": [1, 2, 3], "B": ["x", "y", "z"]})
        right = pd.DataFrame({"A": [1, 2], "C": ["X", "Y"], "D": [0.1, 0.2]})
        result = render(
            left,
            {
                "right_tab": TabOutput(
                    "slug",
                    "name",
                    {
                        "A": RenderColumn("A", "number", "{:,.2f}"),
                        "C": RenderColumn("C", "text", None),
                        "D": RenderColumn("D", "number", "{:,}"),
                    },
                    right,
                ),
                "join_columns": {"on": ["A"], "right": ["C", "D"]},
                "type": "left",
            },
            input_columns={
                "A": RenderColumn("A", "number", "{:d}"),
                "B": RenderColumn("B", "text", None),
            },
        )
        assert_frame_equal(
            result["dataframe"],
            pd.DataFrame(
                {
                    "A": [1, 2, 3],
                    "B": ["x", "y", "z"],
                    "C": ["X", "Y", np.nan],
                    "D": [0.1, 0.2, np.nan],
                }
            ),
        )
        self.assertEqual(result["column_formats"], {"C": None, "D": "{:,}"})

    def test_on_types_differ(self):
        left = pd.DataFrame({"A": [1, 2, 3], "B": ["x", "y", "z"]})
        right = pd.DataFrame({"A": ["1", "2"], "C": ["X", "Y"]})
        result = render(
            left,
            {
                "right_tab": TabOutput(
                    "slug",
                    "Tab 2",
                    {
                        "A": RenderColumn("A", "text", None),
                        "C": RenderColumn("C", "text", None),
                    },
                    right,
                ),
                "join_columns": {"on": ["A"], "right": ["C"]},
                "type": "left",
            },
            input_columns={
                "A": RenderColumn("A", "number", "{}"),
                "B": RenderColumn("B", "text", None),
            },
        )

        self.assertEqual(
            result,
            i18n_message(
                "error.differentColumnTypes",
                {
                    "column_name": "A",
                    "left_type": "number",
                    "right_type": "text",
                    "other_tab_name": "Tab 2",
                },
            ),
        )

    def test_prevent_overwrite(self):
        left = pd.DataFrame({"A": [1, 2, 3], "B": ["x", "y", "z"]})
        right = pd.DataFrame({"A": ["1", "2"], "B": ["X", "Y"]})
        result = render(
            left,
            {
                "right_tab": TabOutput(
                    "slug",
                    "Tab 2",
                    {
                        "A": RenderColumn("A", "number", "{}"),
                        "B": RenderColumn("B", "text", None),
                    },
                    right,
                ),
                "join_columns": {"on": ["A"], "right": ["B"]},
                "type": "left",
            },
            input_columns={
                "A": RenderColumn("A", "number", "{}"),
                "B": RenderColumn("B", "text", None),
            },
        )

        self.assertEqual(
            result,
            i18n_message(
                "error.columnAlreadyExists",
                {"column_name": "B", "other_tab_name": "Tab 2"},
            ),
        )

    def test_left_join_delete_unused_categories_in_added_columns(self):
        left = pd.DataFrame({"A": ["a", "b"]}, dtype="category")
        right = pd.DataFrame(
            {
                "A": pd.Series(["a", "z"], dtype="category"),
                "B": pd.Series(["x", "y"], dtype="category"),
            }
        )
        result = render(
            left,
            {
                "right_tab": TabOutput(
                    "slug",
                    "Tab 2",
                    {
                        "A": RenderColumn("A", "text", None),
                        "B": RenderColumn("B", "text", None),
                    },
                    right,
                ),
                "join_columns": {"on": ["A"], "right": ["B"]},
                "type": "left",
            },
            input_columns={"A": RenderColumn("A", "text", None)},
        )
        # 'z' category does not appear in result, so it should not be a
        # category in the 'B' column.
        assert_frame_equal(
            result["dataframe"],
            pd.DataFrame(
                {
                    "A": pd.Series(["a", "b"], dtype="category"),
                    "B": pd.Series(["x", np.nan], dtype="category"),
                }
            ),
        )

    def test_right_join_delete_unused_categories_in_input_columns(self):
        left = pd.DataFrame(
            {
                "A": pd.Series(["a", "b"], dtype="category"),  # join column
                "B": pd.Series(["c", "d"], dtype="category"),  # other column
            }
        )
        right = pd.DataFrame(
            {"A": pd.Series(["a"], dtype="category"), "C": ["e"]}  # join column
        )
        result = render(
            left,
            {
                "right_tab": TabOutput(
                    "slug",
                    "Tab 2",
                    {
                        "A": RenderColumn("A", "text", None),
                        "C": RenderColumn("C", "text", None),
                    },
                    right,
                ),
                "join_columns": {"on": ["A"], "right": ["C"]},
                "type": "right",
            },
            input_columns={
                "A": RenderColumn("A", "text", None),
                "B": RenderColumn("B", "text", None),
            },
        )
        # 'b' and 'd' categories don't appear in result, so it should not be
        # categories in the result dataframe.
        assert_frame_equal(
            result["dataframe"],
            pd.DataFrame(
                {
                    "A": pd.Series(["a"], dtype="category"),
                    "B": pd.Series(["c"], dtype="category"),
                    "C": ["e"],
                }
            ),
        )

    def test_inner_join_delete_unused_categories_in_all_columns(self):
        left = pd.DataFrame(
            {
                "A": pd.Series(["a", "b"], dtype="category"),  # join column
                "B": pd.Series(["c", "d"], dtype="category"),  # other column
            }
        )
        right = pd.DataFrame(
            {
                "A": pd.Series(["a", "x"], dtype="category"),  # join column
                "C": pd.Series(["e", "y"], dtype="category"),  # other column
            }
        )
        result = render(
            left,
            {
                "right_tab": TabOutput(
                    "slug",
                    "Tab 2",
                    {
                        "A": RenderColumn("A", "text", None),
                        "C": RenderColumn("C", "text", None),
                    },
                    right,
                ),
                "join_columns": {"on": ["A"], "right": ["C"]},
                "type": "inner",
            },
            input_columns={
                "A": RenderColumn("A", "text", None),
                "B": RenderColumn("B", "text", None),
            },
        )
        # 'b', 'd', 'x' and 'y' categories don't appear in the result, so the
        # dtypes should not contain them.
        assert_frame_equal(
            result["dataframe"],
            pd.DataFrame({"A": ["a"], "B": ["c"], "C": ["e"]}, dtype="category"),
        )
