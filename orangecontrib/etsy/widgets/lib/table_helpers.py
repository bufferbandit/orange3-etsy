import operator
from functools import partial

import pandas
import pandas as pd
from AnyQt import QtCore, QtGui
from Orange.data import Table, Domain, ContinuousVariable, DiscreteVariable, TimeVariable
from Orange.widgets.settings import PerfectDomainContextHandler, ContextHandler
from AnyQt.QtWidgets import QItemDelegate, QLineEdit, QCompleter
from AnyQt.QtCore import Qt, QAbstractTableModel, QModelIndex
from Orange.widgets.utils import vartype

from typing import Optional
import numpy as np
import copy

from PyQt5.QtCore import QSortFilterProxyModel
from PyQt5.QtWidgets import QWidgetAction, QStyledItemDelegate, QListWidget, QMenu, QLabel, QHBoxLayout, \
    QListWidgetItem, QStyle, QComboBox

from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLineEdit, QTreeView, QTableView
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QKeySequence
from collections import OrderedDict


class EditableTableItemDelegate(QItemDelegate):
    def createEditor(self, parent, options, index: QModelIndex):
        model = index.model()  # type: EditableTableModel
        if not model.is_discrete(index.column()):
            return super().createEditor(parent, options, index)

        vals = model.discrete_vals(index.column())
        edit = QLineEdit(parent)
        edit.setCompleter(QCompleter(vals, edit, filterMode=Qt.MatchContains))

        def save():
            if edit.text():
                model.setData(index, edit.text())

        edit.editingFinished.connect(save)
        return edit

    def setEditorData(self, editor, index):
        current_val = index.model().data(index, Qt.DisplayRole)
        editor.setText(current_val)


class EditableTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._table = [[None]]
        self._domain = None

    def _var(self, index):
        # todo: remove if/when domain[idx] is fixed
        return (self._domain.variables + self._domain.metas)[index]

    def set_domain(self, domain: Optional[Domain]):
        self._domain = domain
        if domain is not None:
            # Todo: change to len(domain) when Domain len's behaviour is fixed
            n_columns = len(domain.variables) + len(domain.metas)
        else:
            n_columns = 3
        self.setColumnCount(n_columns)
        self.clear()

    def is_discrete(self, column):
        column_data = set(row[column] for row in self._table) - {None}

        def is_number(x):
            """
            Check if x is number
            x.is_digit only works for usigned ints this on works for ints and
            floats
            """
            try:
                float(x)
                return True
            except ValueError:
                return False

        return (
            self._domain is not None
            and self._var(column).is_discrete
            or (
                column_data
                and not self.is_time_variable(column)
                and not all(map(lambda s: is_number(s), column_data))
            )
        )

    def is_time_variable(self, column):
        values = self.time_vals(column)
        return values and not all(e is None for e in values)

    def time_vals(self, column):
        column_data = [row[column] for row in self._table]
        try:
            tvar = TimeVariable("_")
            values = [
                tvar.parse_exact_iso(d) if d is not None else None
                for d in column_data
            ]
            return values
        except ValueError:
            return None

    def discrete_vals(self, column):
        if self._domain is not None and self._var(column).is_discrete:
            return self._var(column).values
        else:
            return list(set(row[column] for row in self._table) - {None})

    def rowCount(self, parent=None):
        return len(self._table)

    def columnCount(self, parent=None):
        return len(self._table[0])

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsEditable

    def data(self, index: QModelIndex, role=None):
        value = self._table[index.row()][index.column()]
        if role == Qt.DisplayRole and value is not None:
            return str(value)
        elif role == Qt.TextAlignmentRole:
            return Qt.AlignVCenter | Qt.AlignLeft

    def setData(self, index: QModelIndex, value: str, role=None):
        value = None if not value else value
        self._table[index.row()][index.column()] = value
        self.dataChanged.emit(index, index)
        return True

    def set_table(self, table):
        self.beginResetModel()
        # must be a copy since model changes it inplace
        self._table = copy.deepcopy(table)
        self.endResetModel()

    def get_raw_table(self):
        # the model updates the table inplace
        return copy.deepcopy(self._table)

    def setRowCount(self, n_rows):
        diff = n_rows - self.rowCount()
        if diff > 0:
            self.beginInsertRows(QModelIndex(), self.rowCount(), n_rows - 1)
            self._table += [[None] * self.columnCount() for _ in range(diff)]
            self.endInsertRows()
        elif diff < 0:
            self.beginRemoveRows(QModelIndex(), n_rows, self.rowCount() - 1)
            del self._table[n_rows:]
            self.endRemoveRows()

    def setColumnCount(self, n_columns):
        diff = n_columns - self.columnCount()
        if diff > 0:
            self.beginInsertColumns(
                QModelIndex(), self.columnCount(), n_columns - 1)
            for row in self._table:
                row += [None] * diff
            self.endInsertColumns()
        elif diff < 0:
            self.beginRemoveColumns(
                QModelIndex(), n_columns, self.columnCount() - 1)
            for row in self._table:
                del row[n_columns:]
            self.endRemoveColumns()

    def headerData(self, section, orientation, role=None):
        if orientation == Qt.Vertical:
            return super().headerData(section, orientation, role)

        if role == Qt.DisplayRole:
            if self._domain is None:
                return str(section + 1)
            else:
                return self._var(section).name

    def clear(self):
        self.set_table(
            [[None] * self.columnCount()
             for _ in range(self.rowCount())]
        )

    def get_table(self):
        domain = self.get_domain()
        data = np.array(self._table)  # type:
        for ci in range(data.shape[1]):
            if isinstance((domain.variables + domain.metas)[ci], TimeVariable):
                data[:, ci] = self.time_vals(ci)
        return Table.from_list(domain, data)

    def get_domain(self):
        if self._domain is not None:
            return self._domain

        vars = []
        for ci in range(self.columnCount()):
            if self.is_discrete(ci):
                values = set(
                    row[ci] for row in self._table if row[ci] is not None
                )
                var = DiscreteVariable(name=str(ci + 1), values=values)
            elif self.is_time_variable(ci):
                var = TimeVariable(name=str(ci + 1))
            else:
                var = ContinuousVariable(name=str(ci + 1))
            vars.append(var)
        return Domain(vars)


class CreateTableContextHandler(PerfectDomainContextHandler):
    def open_context(self, widget, domain):
        ContextHandler.open_context(
            self, widget, domain, *self.encode_domain(domain)
        )

    def encode_domain(self, domain):
        """
        Encode domain into tuples (name, type)
        A tuple is returned for each of attributes, class_vars and metas.
        """
        if self.match_values == self.MATCH_VALUES_ALL:

            def _encode(attrs):
                return tuple(
                    (v.name, list(v.values) if v.is_discrete else vartype(v))
                    for v in attrs
                )

        else:

            def _encode(attrs):
                return tuple((v.name, vartype(v)) for v in attrs)

        if domain is None:
            return (None, None, None)
        return (
            _encode(domain.attributes),
            _encode(domain.class_vars),
            _encode(domain.metas),
        )



class TableHelpersBase:
    def nrows_changed(self):
        self.table_model.setRowCount(self.n_rows)
        self.commit()

    def ncolumns_changed(self):
        self.table_model.setColumnCount(self.n_columns)
        self.commit()

    def data_changed(self):
        self.context_data = self.table_model.get_raw_table()
        self.commit()

    def commit(self):
        data = None
        try:
            data = self.table_model.get_table()
            self.Error.transform_err.clear()
        except Exception as ex:
            self.Error.transform_err()
        self.Outputs.data.send(data)

    # @Inputs.data
    # def set_dataset(self, data):
    #     self.closeContext()
    #     if data is not None:
    #         self.table_model.set_domain(data.domain)
    #         self.context_data = [
    #             [None] * (len(data.domain.variables) + len(data.domain.metas))
    #             for _ in range(self.table_model.rowCount())
    #         ]
    #     else:
    #         self.table_model.set_domain(None)
    #         self.context_data = copy.deepcopy(DEFAULT_DATA)
    #     self.c_spin.setEnabled(data is None)
    #     self.c_spin.setValue(self.table_model.columnCount())
    #     self.openContext(data)
    #     self.unconditional_commit()


class PandasModel(QtCore.QAbstractTableModel):
    def __init__(self, df = pd.DataFrame(), parent=None):
        QtCore.QAbstractTableModel.__init__(self, parent=parent)
        self._df = df.copy()

    def toDataFrame(self):
        return self._df.copy()

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if role != QtCore.Qt.DisplayRole:
            return QtCore.QVariant()

        if orientation == QtCore.Qt.Horizontal:
            try:
                return self._df.columns.tolist()[section]
            except (IndexError, ):
                return QtCore.QVariant()
        elif orientation == QtCore.Qt.Vertical:
            try:
                # return self.df.index.tolist()
                return self._df.index.tolist()[section]
            except (IndexError, ):
                return QtCore.QVariant()

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if role != QtCore.Qt.DisplayRole:
            return QtCore.QVariant()

        if not index.isValid():
            return QtCore.QVariant()

        return QtCore.QVariant(str(self._df.loc[index.row(), index.column()]))

    def setData(self, index, value, role):
        row = self._df.index[index.row()]
        col = self._df.columns[index.column()]
        if hasattr(value, 'toPyObject'):
            # PyQt4 gets a QVariant
            value = value.toPyObject()
        else:
            # PySide gets an unicode
            dtype = self._df[col].dtype
            if dtype != object:
                value = None if value == '' else dtype.type(value)
        self._df.set_value(row, col, value)
        return True

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self._df.index)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return len(self._df.columns)

    def sort(self, column, order):
        colname = self._df.columns.tolist()[column]
        self.layoutAboutToBeChanged.emit()
        self._df.sort_values(colname, ascending= order == QtCore.Qt.AscendingOrder, inplace=True)
        self._df.reset_index(inplace=True, drop=True)
        self.layoutChanged.emit()


class WidgetedCell(object):
    """Set as the value of an element in a pandas DataFrame to create a widget
    NOTE: You may also want your widget to implement the getWidgetedCellState and setWidgetedCellState
    methods so that interactions with the controlls persist.
    """
    def __init__(self, widget):
        """Create a widget in the DataFrameWidget's cell
        Args:
            widget (subclass of QWidget)
                Widget to display in cell.  The constructor of `widget` must
                accept only one argument, the parent widget to
                build `widget` inside of
        """
        self.widget = widget

    def __repr__(self):
        return repr(self.widget)

class DataFrameModel(QtCore.QAbstractTableModel):
    """ data model for a DataFrame class """

    RawDataRole = 64    # Custom Role, http://qt-project.org/doc/qt-4.8/qt.html#ItemDataRole-enum
    RawIndexRole = 65


    def __init__(self):
        super(DataFrameModel, self).__init__()
        self._df = pandas.DataFrame()
        self._orig_df = pandas.DataFrame()
        self._pre_dyn_filter_df = None
        self._resort = lambda : None # Null resort functon


    def setDataFrame(self, dataFrame):
        """Set or change pandas DataFrame to show"""
        self.df = dataFrame
        self._orig_df = dataFrame.copy()
        self._pre_dyn_filter_df = None # Clear dynamic filter

    @property
    def df(self):
        return self._df
    @df.setter
    def df(self, dataFrame):
        """Setter should only be used internal to DataFrameModel.  Others should use setDataFrame()"""
        self.modelAboutToBeReset.emit()
        self._df = dataFrame
        self.modelReset.emit()

    @QtCore.pyqtSlot()
    def beginDynamicFilter(self):
        """Effects of using the "filter" function will not become permanent until endDynamicFilter called"""
        if self._pre_dyn_filter_df is None:
            print("NEW DYNAMIC FILTER MODEL")
            self._pre_dyn_filter_df = self.df.copy()
        else:
            # Already dynamically filtering, so don't override that
            print("SAME DYNAMIC FILTER MODEL")
            pass

    @QtCore.pyqtSlot()
    def endDynamicFilter(self):
        """Makes permanent the effects of the dynamic filter"""
        print(" * * * RESETING DYNAMIC")
        self._pre_dyn_filter_df = None

    @QtCore.pyqtSlot()
    def cancelDynamicFilter(self):
        """Cancel the dynamic filter"""
        self.df = self._pre_dyn_filter_df.copy()
        self._pre_dyn_filter_df = None


    #------------- table display functions -----------------
    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if role != QtCore.Qt.DisplayRole:
            return None

        if orientation == QtCore.Qt.Horizontal:
            try:
                return '%s' % self.df.columns.tolist()[section]
            except (IndexError, ):
                return QtCore.QVariant()
        elif orientation == QtCore.Qt.Vertical:
            try:
                return '%s' % self.df.index.tolist()[section]
            except (IndexError, ):
                return QtCore.QVariant()

    def data(self, index, role=QtCore.Qt.DisplayRole):
        #if role == QtCore.Qt.BackgroundRole:
        #    return QColor(255,255,204)
        if role in (QtCore.Qt.DisplayRole, DataFrameModel.RawDataRole, DataFrameModel.RawIndexRole):
            if not index.isValid():
                return QtCore.QVariant()

            if role == DataFrameModel.RawIndexRole:
                r = self.df.index[index.row()]
                c = self.df.columns[index.column()]
                return (r, c)
            data = self.df.iloc[index.row(), index.column()]


            if role == DataFrameModel.RawDataRole:
                return data

            if pandas.isnull(data):
                return QtCore.QVariant()
            return '%s' % data
        else:
            return None

    def flags(self, index):
        defaults = super(DataFrameModel, self).flags(index)
        data = self.data(index, DataFrameModel.RawDataRole)
        if isinstance(data, WidgetedCell):
            return defaults | QtCore.Qt.ItemIsEditable
        return defaults

    def __setData(self, index, value, role):
        row = self.df.index[index.row()]
        col = self.df.columns[index.column()]
        if hasattr(value, 'toPyObject'):
            # PyQt4 gets a QVariant
            value = value.toPyObject()
        else:
            # PySide gets an unicode
            dtype = self.df[col].dtype
            if dtype != object:
                value = None if value == '' else dtype.type(value)
        self.df.set_value(row, col, value)
        self.dataChanged.emit()
        return True

    def rowCount(self, index=QtCore.QModelIndex()):
        return self.df.shape[0]

    def columnCount(self, index=QtCore.QModelIndex()):
        return self.df.shape[1]

    def sort(self, col_ix, order = QtCore.Qt.AscendingOrder):
        if col_ix >= self.df.shape[1]:
            # Column out of bounds
            return

        self.layoutAboutToBeChanged.emit()
        ascending = True if order == QtCore.Qt.AscendingOrder else False
        self.df = self.df.sort(self.df.columns[col_ix], ascending=ascending)
        self.layoutChanged.emit()

        # Set sorter to current sort (for future filtering)
        self._resort = partial(self.sort, col_ix, order)

    def filter(self, col_ix, needle):
        """Filter DataFrame view.  Case Insenstive.
        Fitlers the DataFrame view to include only rows who's value in col
        contains the needle. EX: a needle of "Ab" will show rows with
        "absolute" and "REABSOLVE".
        Args:
            col_ix (int)
                Column index in df to filter
            needle (str)
                String to search df_view for
        """

        if self._pre_dyn_filter_df is not None:
            df = self._pre_dyn_filter_df.copy()
        else:
            df = self.df
        col = df.columns[col_ix]
        # Create lowercase string version of column as series
        s_lower = df[col].astype('str').str.lower()

        # Make needle lower case too
        needle = str(needle).lower()

        # Actually filter
        self.df = df[s_lower.str.contains(str(needle))]

        # Resort
        self._resort()

    def filterIsIn(self, col_ix, include):
        df = self._orig_df
        col = self.df.columns[col_ix]

        # Convert to string
        s_col = df[col].astype('str')

        # Filter
        self.df = df[s_col.isin(include)]

        # Resort
        self._resort()

    def filterFunction(self, col_ix, function):
        df = self.df
        col = self.df.columns[col_ix]

        self.df = df[function(df[col])]

        # Resort
        self._resort()

    def reset(self):
        self.df = self._orig_df.copy()
        self._resort = lambda: None
        self._pre_dyn_filter_df = None


class DataFrameSortFilterProxyModel(QSortFilterProxyModel):
    def __init__(self):
        super(DataFrameSortFilterProxyModel, self).__init__()

        self._accepted_rows = []
        self._source_df = None
        self._refilter = lambda: None

    def setSourceModel(self, source_model):
        super(DataFrameSortFilterProxyModel, self).setSourceModel(source_model)

        source_model.modelReset.connect(self._source_model_changed)
        self._source_model_changed()

    def sort(self, *args):
        # Delegate sorting to the underyling model
        self.sourceModel().sort(*args)

    def _source_model_changed(self):
        self._source_df = self.sourceModel().df
        # Accept all rows
        self._accepted_rows = range(0, self._source_df.shape[0])
        print("SOURCE MODEL CHANGED", len(self._accepted_rows))
        if len(self._accepted_rows) > 0:
            self.setFilterString('')    # Reset the filter
        self._refilter()

    def setFilterString(self, needle):
        """Filter DataFrame using df[col].str.contains(needle).  Case insensitive."""
        df = self._source_df
        col = df.columns[self.filterKeyColumn()]

        # Create lowercase string version of column as series
        s_lower = df[col].astype('str').str.lower()

        # Make needle lower case too
        needle = str(needle).lower()

        mask = s_lower.str.contains(str(needle))
        self._filter_using_mask(mask)
        self._refilter = partial(self.setFilterString, needle)

    def setFilterList(self, filter_list):
        """Filter DataFrame using df[col].isin(filter_list)."""
        df = self._source_df
        col = df.columns[self.filterKeyColumn()]

        mask = df[col].isin(filter_list)
        self._filter_using_mask(mask)

    def setFilterFunction(self, func):
        """Filter DataFrame using df[col].apply(func).  Func should return True or False"""
        df = self._source_df
        col = df.columns[self.filterKeyColumn()]

        mask = df[col].apply(func)
        self._filter_using_mask(mask)

    def _filter_using_mask(self, mask):
        # Actually filter (need *locations* of filtered values)
        df = self._source_df
        col = df.columns[self.filterKeyColumn()]

        ilocs = pandas.DataFrame(range(len(df)))
        ilocs = ilocs[mask.reset_index(drop=True)]

        self.modelAboutToBeReset.emit()
        self._accepted_rows = ilocs.index
        self.modelReset.emit()


    @property
    def df(self):
        return self._source_df.iloc[self._accepted_rows]
    @df.setter
    def df(self, val):
        raise AttributeError("Tried to set the dataframe of DataFrameSortFilterProxyModel")

    def filterAcceptsRow(self, row, idx):
        return row in self._accepted_rows

    def filterAcceptsColumn(self, col, idx):
        # Columns are hidden manually.  No need for this
        return True

    def setFilterRegExp(self, *args):
        raise NotImplementedError("Use setFilterString, setFilterList, or setFilterFunc instead")

    def setFilterWildcard(self, *args):
        raise NotImplementedError("Use setFilterString, setFilterList, or setFilterFunc instead")

    def setFilterFixedString(self, *args):
        raise NotImplementedError("Use setFilterString, setFilterList, or setFilterFunc instead")


class DynamicFilterLineEdit(QLineEdit):
    """Filter textbox for a DataFrameTable"""
    def __init__(self, *args, **kwargs):
        self._always_dynamic = kwargs.pop('always_dynamic', False)

        super(DynamicFilterLineEdit, self).__init__(*args, **kwargs)

        self.col_to_filter = None
        self._orig_df = None
        self._host = None

    def bind_dataframewidget(self, host, col_ix):
        """Bind tihs DynamicFilterLineEdit to a DataFrameTable's column
        Args:
            host (DataFrameWidget)
                Host to filter
            col_ix (int)
                Index of column of host to filter
        """
        self.host = host
        self.col_to_filter = col_ix
        self.textChanged.connect(self._update_filter)

    @property
    def host(self):
        if self._host is None:
            raise RuntimeError("Must call bind_dataframewidget() "
            "before use.")
        else:
            return self._host
    @host.setter
    def host(self, value):
        if not isinstance(value, DataFrameWidget):
            raise ValueError("Must bind to a DataFrameWidget, not %s" % value)
        else:
            self._host = value

        if not self._always_dynamic:
            self.editingFinished.connect(self._host._data_model.endDynamicFilter)

    def focusInEvent(self, QFocusEvent):
        self._host._data_model.beginDynamicFilter()

    def _update_filter(self, text):
        """Called everytime we type in the filter box"""
        col_ix = self.col_to_filter

        self.host.filter(col_ix, text)


class DynamicFilterMenuAction(QWidgetAction):
    """Filter textbox in column-header right-click menu"""
    def __init__(self, parent, menu, col_ix):
        """Filter textbox in column right-click menu
        Args:
            parent (DataFrameWidget)
                Parent who owns the DataFrame to filter
            menu (QMenu)
                Menu object I am located on
            col_ix (int)
                Index of column used in pandas DataFrame we are to filter
        """
        super(DynamicFilterMenuAction, self).__init__(parent)

        # State
        self.parent_menu = menu

        # Build Widgets
        widget = QWidget()
        layout = QHBoxLayout()
        self.label = QLabel('Filter')
        self.text_box = DynamicFilterLineEdit()
        self.text_box.bind_dataframewidget(self.parent(), col_ix)
        self.text_box.returnPressed.connect(self._close_menu)

        layout.addWidget(self.label)
        layout.addWidget(self.text_box)
        widget.setLayout(layout)

        self.setDefaultWidget(widget)

    def _close_menu(self):
        """Gracefully handle menu"""
        self.parent_menu.close()


class FilterListMenuWidget(QWidgetAction):
    """Filter textbox in column-right click menu"""
    def __init__(self, parent, menu, col_ix):
        """Filter textbox in column right-click menu
        Args:
            parent (DataFrameWidget)
                Parent who owns the DataFrame to filter
            menu (QMenu)
                Menu object I am located on
            col_ix (int)
                Column index used in pandas DataFrame we are to filter
            label (str)
                Label in popup menu
        """
        super(FilterListMenuWidget, self).__init__(parent)

        # State
        self.menu = menu
        self.col_ix = col_ix

        # Build Widgets
        widget = QWidget()
        layout = QVBoxLayout()
        self.list = QListWidget()
        self.list.setFixedHeight(100)

        layout.addWidget(self.list)
        widget.setLayout(layout)

        self.setDefaultWidget(widget)

        # Signals/slots
        self.list.itemChanged.connect(self.on_list_itemChanged)
        self.parent().dataFrameChanged.connect(self._populate_list)

        self._populate_list(inital=True)

    def _populate_list(self, inital=False):
        self.list.clear()

        df = self.parent()._data_model._orig_df
        col = df.columns[self.col_ix]
        full_col = set(df[col])  # All Entries possible in this column
        disp_col = set(self.parent().df[col]) # Entries currently displayed

        def _build_item(item, state=None):
            i = QListWidgetItem('%s' % item)
            i.setFlags(i.flags() | QtCore.Qt.ItemIsUserCheckable)
            if state is None:
                if item in disp_col:
                    state = QtCore.Qt.Checked
                else:
                    state = QtCore.Qt.Unchecked
            i.setCheckState(state)
            i.checkState()
            self.list.addItem(i)
            return i

        # Add a (Select All)
        if full_col == disp_col:
            select_all_state = QtCore.Qt.Checked
        else:
            select_all_state = QtCore.Qt.Unchecked
        self._action_select_all = _build_item('(Select All)', state=select_all_state)

        # Add filter items
        if inital:
            build_list = full_col
        else:
            build_list = disp_col
        for i in sorted(build_list):
            _build_item(i)

        # Add a (Blanks)
        # TODO

    def on_list_itemChanged(self, item):
        ###
        # Figure out what "select all" check-box state should be
        ###
        self.list.blockSignals(True)
        if item is self._action_select_all:
            # Handle "select all" item click
            if item.checkState() == QtCore.Qt.Checked:
                state = QtCore.Qt.Checked
            else:
                state = QtCore.Qt.Unchecked
            # Select/deselect all items
            for i in range(self.list.count()):
                if i is self._action_select_all: continue
                i = self.list.item(i)
                i.setCheckState(state)
        else:
            # Non "select all" item; figure out what "select all" should be
            if item.checkState() == QtCore.Qt.Unchecked:
                self._action_select_all.setCheckState(QtCore.Qt.Unchecked)
            else:
                # "select all" only checked if all other items are checked
                for i in range(self.list.count()):
                    i = self.list.item(i)
                    if i is self._action_select_all: continue
                    if i.checkState() == QtCore.Qt.Unchecked:
                        self._action_select_all.setCheckState(QtCore.Qt.Unchecked)
                        break
                else:
                    self._action_select_all.setCheckState(QtCore.Qt.Checked)
        self.list.blockSignals(False)

        ###
        # Filter dataframe according to list
        ###
        include = []
        for i in range(self.list.count()):
            i = self.list.item(i)
            if i is self._action_select_all: continue
            if i.checkState() == QtCore.Qt.Checked:
                include.append(str(i.text()))

        self.parent().blockSignals(True)
        self.parent().filterIsIn(self.col_ix, include)
        self.parent().blockSignals(False)
        self.parent()._enable_widgeted_cells()

class DataFrameItemDelegate(QStyledItemDelegate):
    """Implements WidgetedCell"""

    def __init__(self):
        super(DataFrameItemDelegate, self).__init__()
        self._cell_widget_states = {}


    def createEditor(self, parent, option, index):
        data = index.data(DataFrameModel.RawDataRole)
        true_index = index.data(DataFrameModel.RawIndexRole)
        if isinstance(data, WidgetedCell):
            # Make new widget
            widget_class = data.widget
            # Give out widget our cell parent so it knows where to paint
            widget = widget_class(parent)
            try:
                # Find existing widget if we can
                widget_state = self._cell_widget_states[true_index]
            except KeyError:
                pass
            else:
                try:
                    widget.setWidgetedCellState(widget_state)
                except AttributeError:
                    # Not implementing the WidgetedCell interface
                    pass
            return widget
        else:
            return super(DataFrameItemDelegate, self).createEditor(parent, option, index)


    def setModelData(self, widget, model, index):
        # Try to save the state of the widget
        try:
            widget_state = widget.getWidgetedCellState()
        except AttributeError:
            # Not implementing the WidgetedCell interface
            return
        true_index = index.data(DataFrameModel.RawIndexRole)
        self._cell_widget_states[true_index] = widget_state



    def paint(self, painter, option, index):
        d = index.data(DataFrameModel.RawDataRole)
        if isinstance(d, WidgetedCell):
            # Don't paint, create editor instead
            return None
        else:
            return super(DataFrameItemDelegate, self).paint(painter, option, index)


class DataFrameWidget(QTableView):

    dataFrameChanged = QtCore.pyqtSignal()
    cellClicked = QtCore.pyqtSignal(int, int)

    def __init__(self, parent=None, df=None):
        """DataFrameTable
        Create a widget to display a pandas DataFrame.
        Args:
            parent (QObject)
                Parent object (likely window or canvas)
            df (pandas DataFrame, optional)
                DataFrame to display
        """
        super(DataFrameWidget, self).__init__(parent)


        self.defaultExcelFile = "temp.xls"
        self.defaultExcelSheet = "Output"

        # Set up view
        self._data_model = DataFrameModel()
        self.setModel(self._data_model)

        # Signals/Slots
        self._data_model.modelReset.connect(self.dataFrameChanged)
        self._data_model.dataChanged.connect(self.dataFrameChanged)
        self.clicked.connect(self._on_click)
        self.dataFrameChanged.connect(self._enable_widgeted_cells)

        # Set up delegate Delegate
        delegate = DataFrameItemDelegate()
        self.setItemDelegate(delegate)
        # Show the edit widget as soon as the user clicks in the cell
        #  (needed for item delegate)
        self.setEditTriggers(self.CurrentChanged)

        # Initilize to passed dataframe
        if df is None:
            df = pandas.DataFrame()
        self._data_model.setDataFrame(df)


        #self.setSortingEnabled(True)

        # Create header menu bindings
        self.horizontalHeader().setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self._header_menu)

        self._enable_widgeted_cells()

    def make_cell_context_menu(self, menu, row_ix, col_ix):
        """Create the mneu displayed when right-clicking on a cell.
        Overrite this method to add custom right-click options
        Args:
            menu (QMenu)
                Menu to which to add actions
            row_ix (int)
                Row location in dataframe
            col_ix (int)
                Coloumn location in dataframe
        Returns:
            menu (QMenu)
                Same menu passed in, with added actions
        """
        cell_val = self.df.iget_value(row_ix, col_ix)

        # Quick Filter
        def _quick_filter(s_col):
            return s_col == cell_val
        menu.addAction(self._icon('CommandLink'),
            "Quick Filter", partial(self._data_model.filterFunction, col_ix=col_ix, function=_quick_filter))

        # GreaterThan/LessThan filter
        def _cmp_filter(s_col, op):
            return op(s_col, cell_val)
        menu.addAction("Show Greater Than",
                        partial(self._data_model.filterFunction, col_ix=col_ix,
                                function=partial(_cmp_filter, op=operator.ge)))
        menu.addAction("Show Less Than",
                        partial(self._data_model.filterFunction, col_ix=col_ix,
                                function=partial(_cmp_filter, op=operator.le)))
        menu.addAction(self._icon('DialogResetButton'),
                        "Clear",
                        self._data_model.reset)
        menu.addSeparator()

        # Save to Excel
        def _to_excel():
            from subprocess import Popen
            self.df.to_excel(self.defaultExcelFile, self.defaultExcelSheet)
            Popen(self.defaultExcelFile, shell=True)
        menu.addAction("Open in Excel",
                       _to_excel)

        return menu


    def contextMenuEvent(self, event):
        """Implements right-clicking on cell.
        NOTE: You probably want to overrite make_cell_context_menu, not this
        function, when subclassing.
        """
        row_ix = self.rowAt(event.y())
        col_ix = self.columnAt(event.x())

        if row_ix < 0 or col_ix < 0:
            return #out of bounds

        menu = QMenu(self)
        menu = self.make_cell_context_menu(menu, row_ix, col_ix)
        menu.exec_(self.mapToGlobal(event.pos()))

    def _header_menu(self, pos):
        """Create popup menu used for header"""
        menu = QMenu(self)
        col_ix = self.horizontalHeader().logicalIndexAt(pos)

        if col_ix == -1:
            # Out of bounds
            return

        # Filter Menu Action
        menu.addAction(DynamicFilterMenuAction(self, menu, col_ix))
        menu.addAction(FilterListMenuWidget(self, menu, col_ix))
        menu.addAction(self._icon('DialogResetButton'),
                        "Reset",
                        self._data_model.reset)

        # Sort Ascending/Decending Menu Action
        menu.addAction(self._icon('TitleBarShadeButton'),
                        "Sort Ascending",
                       partial(self._data_model.sort, col_ix=col_ix, order=QtCore.Qt.AscendingOrder))
        menu.addAction(self._icon('TitleBarUnshadeButton'),
                        "Sort Descending",
                       partial(self._data_model.sort, col_ix=col_ix, order=QtCore.Qt.DescendingOrder))
        menu.addSeparator()

        # Hide
        menu.addAction("Hide", partial(self.hideColumn, col_ix))

        # Show (column to left and right)
        for i in (-1, 1):
            if self.isColumnHidden(col_ix+i):
                menu.addAction("Show %s" % self._data_model.headerData(col_ix+i, QtCore.Qt.Horizontal),
                                partial(self.showColumn, col_ix+i))

        menu.exec_(self.mapToGlobal(pos))


    def setDataFrame(self, df):
        self._data_model.setDataFrame(df)
        self.resizeColumnsToContents()

    def filter(self, col_ix, needle):
        return self._data_model.filter(col_ix, needle)

    def filterIsIn(self, col_ix, include):
        return self._data_model.filterIsIn(col_ix, include)

    @property
    def df(self):
        return self._data_model.df
    @df.setter
    def df(self, dataFrame):
        # Use the "hard setting" of the dataframe because anyone who's interacting with the
        #  DataFrameWidget (ie, end user) would be setting this
        self._data_model.setDataFrame(dataFrame)

    def keyPressEvent(self, event):
        """Implements keyboard shortcuts"""
        if event.matches(QKeySequence.Copy):
            self.copy()
        else:
            # Pass up
            super(DataFrameWidget, self).keyPressEvent(event)

    def copy(self):
        """Copy selected cells into copy-buffer"""
        selection = self.selectionModel()
        indexes = selection.selectedIndexes()
        if len(indexes) < 1:
            # Nothing selected
            return

        # Capture selection into a DataFrame
        items = pandas.DataFrame()
        for idx in indexes:
            row = idx.row()
            col = idx.column()
            item = idx.data()
            if item:
                items = items.set_value(row, col, str(item.toString()))

        # Make into tab-delimited text (best for Excel)
        items = list(items.itertuples(index=False))
        s = '\n'.join(['\t'.join([cell for cell in row]) for row in items])

        # Send to clipboard
        QApplication.clipboard().setText(s)


    def _icon(self, icon_name):
        """Convinence function to get standard icons from Qt"""
        if not icon_name.startswith('SP_'):
            icon_name = 'SP_' + icon_name
        icon = getattr(QStyle, icon_name, None)
        if icon is None:
            raise Exception("Unknown icon %s" % icon_name)
        return self.style().standardIcon(icon)

    def _on_click(self, index):
        if index.isValid():
            self.cellClicked.emit(index.row(), index.column())

    def _enable_widgeted_cells(self):
        # Update all cells with WidgetedCell to have persistent editors
        model = self.model()
        if model is None:
            return
        for r in range(model.rowCount()):
            for c in range(model.columnCount()):
                idx = model.index(r,c)
                d = model.data(idx, DataFrameModel.RawDataRole)
                if isinstance(d, WidgetedCell):
                    self.openPersistentEditor(idx)


class DataFrameApp(QMainWindow):
    """Sample DataFrameTable Application"""
    def __init__(self, df, title="Inspecting DataFrame"):
        super(DataFrameApp, self).__init__()

        # State variables
        self.title_base = title

        # Initialize main data table
        self.table = DataFrameWidget(self)
        self.table.dataFrameChanged.connect(self.datatable_updated)
        self.table.setDataFrame(df)
        self.setCentralWidget(self.table)

        # Set window size
        col_size = sum([self.table.columnWidth(i) for i in range(0,99)])
        col_size = min(col_size+75, 1500)
        self.setGeometry(300, 300, col_size, 250)


    def datatable_updated(self):
        # Change title to reflect updated size
        df = self.table.df
        title = self.title_base + ' [%dx%d]' % (len(df.index), len(df.columns))
        self.setWindowTitle(title)

class ExampleWidgetForWidgetedCell(QComboBox):
    """
    To implement a persistent state for the widgetd cell, you must provide
    a `getWidgetedCellState` and `setWidgetedCellState` methods.  This is how
    the WidgetedCell framework can create and destory your widget as needed.
    """
    def __init__(self, parent):
        super(ExampleWidgetForWidgetedCell, self).__init__(parent)
        self.addItem("Option A")
        self.addItem("Option B")
        self.addItem("Option C")
        self.setCurrentIndex(0)


    def getWidgetedCellState(self):
        return self.currentIndex()

    def setWidgetedCellState(self, state):
        self.setCurrentIndex(state)



class ObjConverter(QStandardItemModel):
    def __init__(self, obj, name='', *args, **kwargs):
        super(ObjConverter, self).__init__(*args, **kwargs)
        self.invisibleRootItem().appendRows(self.convert(obj))
        self.setHorizontalHeaderItem(0, QStandardItem(name))

    def pack(self, item):
        if item.rowCount() == 1 and item.child(0).rowCount() == 0:
            item.setText('%s: %s' % (item.text(), item.child(0).text()))
            #item.parent().setChild(item.row(), 1, QStandardItem(item.child(0).text()))
            item.removeRow(0)

    def setObj(self, obj):
        self.clear()
        self.invisibleRootItem().appendRows(self.convert(obj))

    def convert(self, obj):
        if isinstance(obj, list):
            ret = []
            for n, sub in enumerate(obj):
                item = QStandardItem(str(n))
                item.appendRows(self.convert(sub))
                self.pack(item)
                ret.append(item)
            return ret
        elif isinstance(obj, dict):
            ret = []
            for k in sorted(obj):
                item = QStandardItem(k)
                item.appendRows(self.convert(obj[k]))
                self.pack(item)
                ret.append(item)
            return ret
        return [QStandardItem(repr(obj))]


class ObjTable(QStandardItemModel):
    def __init__(self, obj, *args, **kwargs):
        super(ObjTable, self).__init__(*args, **kwargs)
        self.setObj(obj)

    def _makeItem(self, item):
        return QStandardItem(repr(item))

    def setObj(self, ls):
        if isinstance(ls, list) and all(isinstance(obj, dict) for obj in ls):
            pass
        elif isinstance(ls, dict) and all(isinstance(obj, list) for obj in ls.values()):
            def get(l, n):
                try:
                    return l[n]
                except IndexError:
                    return None

            nrows = max(len(v) for v in ls.values())
            ls = [OrderedDict((k, get(ls[k], n)) for k in ls) for n in range(nrows)]

        keys = list(OrderedDict((k, 0) for obj in ls for k in obj.keys()))
        for n, k in enumerate(keys):
            self.setHorizontalHeaderItem(n, QStandardItem(k))
        for obj in ls:
            self.appendRow([self._makeItem(obj.get(k)) for k in keys])