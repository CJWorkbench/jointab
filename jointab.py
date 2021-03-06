from typing import FrozenSet, List
from cjwmodule import i18n


def _parse_colnames(val: List[str], valid: FrozenSet[str]) -> List[str]:
    return [c for c in val if c in valid]


def render(table, params, *, input_columns):
    right_tab = params["right_tab"]
    if right_tab is None:
        # User hasn't chosen tabs yet
        return table

    right_dataframe = right_tab.dataframe
    on_columns = _parse_colnames(
        params["join_columns"]["on"],
        # Workbench doesn't test whether the 'on' columns are in
        # right_dataframe, but the UI does so we can just ignore any invalid
        # columns and call it a day.
        frozenset(table.columns & right_dataframe.columns),
    )
    on_columns_set = frozenset(on_columns)
    if params["join_columns"]["rightAll"]:
        allowed_right_columns_set = frozenset(right_dataframe.columns).difference(
            frozenset(table.columns)
        )
        right_columns_set = allowed_right_columns_set
    else:
        right_columns_set = frozenset(
            _parse_colnames(
                params["join_columns"]["right"],
                frozenset(right_dataframe.columns).difference(on_columns_set),
            )
        )
    # order right_columns as they're ordered in right_dataframe
    right_columns = [c for c in right_dataframe.columns if c in right_columns_set]

    join_type = params["type"]

    # Ensure all "on" types match
    for colname in on_columns:
        left_type = input_columns[colname].type
        right_type = right_tab.columns[colname].type
        if left_type != right_type:
            return i18n.trans(
                "error.differentColumnTypes",
                'Column "{column_name}" is *{left_type}* in this tab '
                "and *{right_type}* in {other_tab_name}. Please convert "
                "one or the other so they are both the same type.",
                {
                    "column_name": colname,
                    "left_type": left_type,
                    "right_type": right_type,
                    "other_tab_name": right_tab.name,
                },
            )

    # Ensure we don't overwrite a column (the user won't want that)
    for colname in right_columns:
        if colname in input_columns:
            return i18n.trans(
                "error.columnAlreadyExists",
                'You tried to add "{column_name}" from {other_tab_name}, but '
                "your table already has that column. Please rename the column "
                "in one of the tabs, or unselect the column.",
                {"column_name": colname, "other_tab_name": right_tab.name},
            )

    if not on_columns:
        # Pandas ValueError: not enough values to unpack (expected 3, got 0)
        #
        # Let's pretend we want this behavior, and just pass the input
        # (suggesting to the user that the params aren't all entered yet).
        return table

    for on_column in on_columns:
        # if both 'left' and 'right' are categorical, coerce the categories to
        # be identical, so DataFrame.merge can preserve the Categorical dtype.
        # In cases where Categorical is the dtype we want, the join will be
        # faster and the result will take less RAM and disk space.
        #
        # If we don't do this, the result will have 'object' dtype.
        left_series = table[on_column]
        right_series = right_dataframe[on_column]
        if hasattr(left_series, "cat") and hasattr(right_series, "cat"):
            # sorted for ease of unit-testing
            categories = sorted(
                list(
                    frozenset.union(
                        frozenset(left_series.cat.categories),
                        frozenset(right_series.cat.categories),
                    )
                )
            )
            left_series.cat.set_categories(categories, inplace=True)
            right_series.cat.set_categories(categories, inplace=True)

    # Select only the columns we want
    right_dataframe = right_dataframe[on_columns + right_columns]

    dataframe = table.merge(right_dataframe, on=on_columns, how=join_type)

    colnames_to_recategorize = None
    if join_type == "left":
        colnames_to_recategorize = on_columns + right_columns
    elif join_type == "right":
        colnames_to_recategorize = list(input_columns.keys())
    else:
        colnames_to_recategorize = dataframe.columns
    for colname in colnames_to_recategorize:
        series = dataframe[colname]
        if hasattr(series, "cat"):
            series.cat.remove_unused_categories(inplace=True)

    return {
        "dataframe": dataframe,
        "column_formats": {c: right_tab.columns[c].format for c in right_columns},
    }


def _migrate_params_v0_to_v1(params):
    """
    v0: 'type' is index into ['left', 'inner', 'right']; 'join_columns' are
    comma-separated strs.

    v1: 'type' is one of {'left', 'inner', 'right'}; 'join_columns' are
    List[str].
    """
    return {
        **params,
        "join_columns": {
            "on": [c for c in params["join_columns"]["on"].split(",") if c],
            "right": [c for c in params["join_columns"]["right"].split(",") if c],
        },
        "type": ["left", "inner", "right"][params["type"]],
    }


def _migrate_params_v1_to_v2(params):
    """v1: missing 'rightAll'; v2 has it (False for backwards-compat)."""
    return {**params, "join_columns": {**params["join_columns"], "rightAll": False}}


def migrate_params(params):
    if isinstance(params["type"], int):
        params = _migrate_params_v0_to_v1(params)
    if "rightAll" not in params["join_columns"]:
        params = _migrate_params_v1_to_v2(params)
    return params
