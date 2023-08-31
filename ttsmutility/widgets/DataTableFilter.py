from itertools import zip_longest

from rich.text import Text, TextType
from textual._two_way_dict import TwoWayDict
from textual.widgets import DataTable
from textual.widgets.data_table import (
    CellDoesNotExist,
    Row,
    RowKey,
    ColumnKey,
    CellType,
)
from typing_extensions import Self


class DataTableFilter(DataTable):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._unfiltered_data: None | dict[RowKey, dict[ColumnKey, CellType]] = None
        self._unfiltered_rows: None | dict[RowKey, Row] = None

    def filter(self, column: str, f: str) -> Self:
        if f == "":
            if self._unfiltered_data is not None:
                self._data = self._unfiltered_data
                self._unfiltered_data = None

                self.rows = self._unfiltered_rows
                self._unfiltered_rows = None
        else:
            if self._unfiltered_data is None:
                self._unfiltered_data = self._data
                self._unfiltered_rows = self.rows

            self._data = dict(
                filter(
                    lambda x: True if f.lower() in str(x[1][column]).lower() else False,
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

        if self._unfiltered_data is not None:
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

        if self._unfiltered_data is not None:
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
            del self._unfiltered_rows[row_key]
            del self.__unfiltered_data[row_key]

    def remove_column(self, column_key: ColumnKey | str) -> None:
        super().remove_column(column_key)

        if self._unfiltered_data is not None:
            for row in self._unfiltered_data:
                del self._unfiltered_data[row][column_key]
