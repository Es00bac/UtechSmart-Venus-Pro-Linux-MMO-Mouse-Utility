"""List models the QindaTK front end binds to.

``DictListModel`` is a small ``QAbstractListModel`` over a list of dicts:
every key becomes a QML role, rows can be replaced wholesale or edited in
place, and in-place edits emit ``dataChanged`` so a delegate that is being
edited (a delay field, a DPI field) keeps its focus.
"""

from __future__ import annotations

from typing import Iterable

from PyQt6 import QtCore


class DictListModel(QtCore.QAbstractListModel):
    countChanged = QtCore.pyqtSignal()

    def __init__(self, keys: Iterable[str], parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._keys = list(keys)
        self._roles = {QtCore.Qt.ItemDataRole.UserRole + index: key.encode()
                       for index, key in enumerate(self._keys)}
        self._role_of = {key: role for role, key in
                         ((role, name.decode()) for role, name in self._roles.items())}
        self._rows: list[dict] = []

    # -- QAbstractListModel -----------------------------------------------
    def roleNames(self):  # noqa: N802 - Qt API
        return self._roles

    def rowCount(self, parent=QtCore.QModelIndex()):  # noqa: N802 - Qt API
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        key = self._roles.get(role)
        if key is None:
            return None
        return self._rows[index.row()].get(key.decode())

    # -- Python side -------------------------------------------------------
    @property
    def rows(self) -> list[dict]:
        return self._rows

    def set_rows(self, rows: Iterable[dict]) -> None:
        self.beginResetModel()
        self._rows = [dict(row) for row in rows]
        self.endResetModel()
        self.countChanged.emit()

    def update_row(self, row: int, **changes) -> None:
        if not 0 <= row < len(self._rows):
            return
        self._rows[row].update(changes)
        roles = [self._role_of[key] for key in changes if key in self._role_of]
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, roles)

    def update_all(self, transform) -> None:
        """Apply ``transform(row_dict) -> changes`` to every row in place."""
        for row, data in enumerate(self._rows):
            changes = transform(data)
            if changes:
                self.update_row(row, **changes)

    def insert_row(self, row: int, data: dict) -> None:
        row = max(0, min(row, len(self._rows)))
        self.beginInsertRows(QtCore.QModelIndex(), row, row)
        self._rows.insert(row, dict(data))
        self.endInsertRows()
        self.countChanged.emit()

    def remove_row(self, row: int) -> None:
        if not 0 <= row < len(self._rows):
            return
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        del self._rows[row]
        self.endRemoveRows()
        self.countChanged.emit()

    def remove_rows(self, rows: Iterable[int]) -> None:
        for row in sorted(set(rows), reverse=True):
            self.remove_row(row)

    def move_row(self, row: int, target: int) -> None:
        """Move one row to ``target`` (its index after the move)."""
        if row == target or not (0 <= row < len(self._rows)) or not (0 <= target < len(self._rows)):
            return
        destination = target + 1 if target > row else target
        if not self.beginMoveRows(QtCore.QModelIndex(), row, row, QtCore.QModelIndex(), destination):
            return
        self._rows.insert(target, self._rows.pop(row))
        self.endMoveRows()

    def clear(self) -> None:
        self.set_rows([])

    # -- QML side ----------------------------------------------------------
    @QtCore.pyqtProperty(int, notify=countChanged)
    def count(self) -> int:
        return len(self._rows)

    @QtCore.pyqtSlot(int, result="QVariant")
    def get(self, row: int):
        if 0 <= row < len(self._rows):
            return dict(self._rows[row])
        return {}

    @QtCore.pyqtSlot(str, "QVariant", result=int)
    def indexOf(self, key: str, value) -> int:  # noqa: N802 - QML-facing
        for row, data in enumerate(self._rows):
            if data.get(key) == value:
                return row
        return -1
