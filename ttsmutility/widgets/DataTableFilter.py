from itertools import zip_longest
from operator import itemgetter
from typing import Any

from rich.text import Text, TextType
from textual._two_way_dict import TwoWayDict
from textual.widgets import DataTable
from textual.widgets.data_table import (
    CellDoesNotExist,
    CellType,
    ColumnKey,
    Row,
    RowKey,
)
from typing_extensions import Self
from ..utility.util import unsizeof_fmt
from textual.events import Blur, Focus


class DataTableFilter(DataTable):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._unfiltered_data: None | dict[RowKey, dict[ColumnKey, CellType]] = None
        self._unfiltered_rows: None | dict[RowKey, Row] = None

    def on_blur(self, event: Blur):
        self.show_cursor = False

    def on_focus(self, event: Focus):
        self.show_cursor = True

    def filter(self, f: str, *columns: str) -> Self:
        if f == "":
            if self._unfiltered_data is not None:
                self._data = self._unfiltered_data
                self._unfiltered_data = None
            if self._unfiltered_rows is not None:
                self.rows = self._unfiltered_rows
                self._unfiltered_rows = None
        else:
            if self._unfiltered_data is None:
                self._unfiltered_data = self._data
            if self._unfiltered_rows is None:
                self._unfiltered_rows = self.rows

            def multi_col_filter(x):
                for col in columns:
                    if f.lower() in str(x[1][col]).lower():
                        return True
                return False

            self._data = dict(
                filter(
                    multi_col_filter,
                    self._unfiltered_data.items(),
                )
            )
            self.rows = dict(
                [
                    (row_key, self._unfiltered_rows[row_key])
                    for row_key in self._data.keys()
                ]
            )

        self._row_locations = TwoWayDict(
            {key: new_index for new_index, (key, _) in enumerate(self._data.items())}
        )
        self._update_count += 1
        self._require_update_dimensions = True
        self.refresh()
        return self

    def sort(
        self,
        *columns: ColumnKey | str,
        reverse: bool = False,
        is_size: bool = False,
    ) -> Self:
        """Sort the rows in the `DataTable` by one or more column keys.

        Args:
            columns: One or more columns to sort by the values in.
            reverse: If True, the sort order will be reversed.

        Returns:
            The `DataTable` instance.
        """

        def sort_by_column_keys(
            row: tuple[RowKey, dict[ColumnKey | str, CellType]]
        ) -> Any:
            _, row_data = row
            result = itemgetter(*columns)(row_data)
            if "size" in columns:
                result = unsizeof_fmt(result)
            return result

        ordered_rows = sorted(
            self._data.items(), key=sort_by_column_keys, reverse=reverse
        )
        self._row_locations = TwoWayDict(
            {key: new_index for new_index, (key, _) in enumerate(ordered_rows)}
        )
        self._update_count += 1
        self.refresh()
        return self

    def update_cell(
        self,
        row_key: RowKey | str,
        column_key: ColumnKey | str,
        value: CellType,
        *,
        update_width: bool = False,
    ) -> None:
        if self._unfiltered_data is not None:
            try:
                self._unfiltered_data[row_key][column_key] = value
            except KeyError:
                raise CellDoesNotExist(
                    f"No cell exists for row_key={row_key!r}, column_key={column_key!r}."
                ) from None

        return super().update_cell(
            row_key, column_key, value, update_width=update_width
        )

    def clear(self, columns: bool = False) -> Self:
        self._unfiltered_data = None
        self._unfiltered_rows = None
        return super().clear(columns)

    def add_column(
        self,
        label: TextType,
        *,
        width: int | None = None,
        key: str | None = None,
        default: CellType | None = None,
    ) -> ColumnKey:
        column_key = super().add_column(label, width=width, key=key, default=default)

        if self._unfiltered_data is not None and self._unfiltered_rows is not None:
            # Update pre-existing rows to account for the new column.
            for row_key in self._unfiltered_rows.keys():
                self._unfiltered_data[row_key][column_key] = default

        return column_key

    def add_row(
        self,
        *cells: CellType,
        height: int = 1,
        key: str | None = None,
        label: TextType | None = None,
    ) -> RowKey:
        row_key = super().add_row(*cells, height=height, key=key, label=label)

        if self._unfiltered_data is not None and self._unfiltered_rows is not None:
            self._unfiltered_data[row_key] = {
                column.key: cell
                for column, cell in zip_longest(self.ordered_columns, cells)
            }
            label = Text.from_markup(label) if isinstance(label, str) else label
            self._unfiltered_rows[row_key] = Row(row_key, height, label)

        return row_key

    def remove_row(self, row_key: RowKey | str) -> None:
        super().remove_row(row_key)
        if self._unfiltered_data is not None:
            del self._unfiltered_data[row_key]
        if self._unfiltered_rows is not None:
            del self._unfiltered_rows[row_key]

    def remove_column(self, column_key: ColumnKey | str) -> None:
        super().remove_column(column_key)

        if self._unfiltered_data is not None and self._unfiltered_rows is not None:
            for row in self._unfiltered_data:
                del self._unfiltered_data[row][column_key]
