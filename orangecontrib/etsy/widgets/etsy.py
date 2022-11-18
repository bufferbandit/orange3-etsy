import copy
import pprint
from typing import Optional

import numpy as np
from AnyQt import QtCore, QtGui
from AnyQt.QtCore import Qt, QAbstractTableModel, QModelIndex, QSize
from AnyQt.QtWidgets import QTableView, QItemDelegate, QLineEdit, QCompleter, QWidget

from Orange.data import (
    Table, Domain,
    ContinuousVariable,
    DiscreteVariable,
    TimeVariable,
)
from Orange.widgets import gui
from Orange.widgets.settings import (
    Setting, ContextSetting,
    PerfectDomainContextHandler, ContextHandler
)
from Orange.widgets.utils import vartype
from Orange.widgets.utils.widgetpreview import WidgetPreview
from Orange.widgets.widget import OWWidget, Output, Input, Msg
from PyQt5.QtCore import QByteArray

from AnyQt import QtWidgets
from PyQt5.QtWidgets import QTreeWidgetItem, QTreeView, QInputDialog, QCheckBox

from orangecontrib.etsy.widgets.lib.etsy_api_client import EtsyOAuth2Client
from orangecontrib.etsy.widgets.lib.searchbar_helpers import SearchBarComboBox
from orangecontrib.etsy.widgets.lib.table_helpers import (
    TableHelpersBase, CreateTableContextHandler,
    EditableTableItemDelegate, EditableTableModel)
from orangecontrib.etsy.widgets.lib.tree_helpers import DictTreeModel

DEFAULT_DATA = [[None] * 6 for y in range(20)]


class OWCreateTable(TableHelpersBase, OWWidget):
    name = "Etsy API"
    description = "Orange widget for using the Etsy API and its data."
    icon = "icons/etsy_icon_round.svg"
    priority = 100
    keywords = ["Etsy", "API", "data", "web", "table"]

    class Outputs:
        data = Output("Data", Table)

    class Error(OWWidget.Error):
        transform_err = Msg("Data does not fit to domain")

    settingsHandler = CreateTableContextHandler()

    n_rows = Setting(len(DEFAULT_DATA))
    n_columns = Setting(len(DEFAULT_DATA[0]))
    auto_commit = Setting(True)
    # since data is a small (at most 20x20) table we can afford to store it
    # as a context
    context_data = ContextSetting(copy.deepcopy(DEFAULT_DATA), schema_only=True)
    etsy_api_function_params = []

    search_items = []


    #
    ETSY_API_TOKEN = None
    ETSY_AUTO_CLOSE_BROWSER = True
    ETSY_AUTO_REFRESH_TOKEN = True
    ETSY_AUTO_START_AUTH = True
    ETSY_VERBOSE = False
    ETSY_HOST = "localhost"
    ETSY_PORT = 5000

    ETSY_API_CLIENT = None

    ETSY_ROUTES = []

    def __init__(self):
        super().__init__()
        self.setup_ui()




    def setup_ui(self):
        def setup_sidebar(self):

            def setup_control_box(self):
                # Controls box
                self.controlBox = gui.vBox(self.controlArea, "Control")

                # Set alignment top
                self.controlBox.layout().setAlignment(Qt.AlignTop)
                self.controlArea.layout().setAlignment(Qt.AlignTop)

                self.controlBox.setMinimumWidth(250)




            def setup_info_box(self):
                # Info box
                # info_box = gui.widgetBox(self.controls_box, "Info")
                # self.infoa = gui.widgetLabel(info_box, 'No data on input yet, waiting to get something.')
                # self.r_spin = gui.spin(info_box, self, "n_rows", 1, 2000, 1, labelWidth=100, controlWidth=50,
                #                        label="Rows:",
                #                        callback=self.nrows_changed)
                # self.c_spin = gui.spin(info_box, self, "n_columns", 1, 2000, 1, labelWidth=100, controlWidth=50,
                #                        label="Columns:",
                #                        callback=self.ncolumns_changed)
                # gui.separator(self.controls_box)


                # self.check_ETSY_AUTO_CLOSE_BROWSER = QCheckBox('ETSY_AUTO_CLOSE_BROWSER', self.controls_box)


                self.check_ETSY_AUTO_CLOSE_BROWSER = gui.checkBox(
                        self.controlBox, self,
                        value="ETSY_AUTO_CLOSE_BROWSER",
                        label="(Etsy) Auto close browser")

                self.check_ETSY_AUTO_REFRESH_TOKEN = gui.checkBox(
                        self.controlBox, self,
                        value="ETSY_AUTO_REFRESH_TOKEN",
                        label="(Etsy) Auto refresh token")

                self.check_ETSY_AUTO_START_AUTH = gui.checkBox(
                        self.controlBox, self,
                        value="ETSY_AUTO_START_AUTH",
                        label="(Etsy) Auto start auth")

                self.check_ETSY_VERBOSE = gui.checkBox(
                        self.controlBox, self,
                        value="ETSY_VERBOSE",
                        label="(Etsy) Log to stdout")

                self.check_ETSY_HOST = gui.lineEdit(
                        self.controlBox, self,
                        value="ETSY_HOST",
                        label="(Etsy) Host")
                # set max with of the input field to 100
                # self.check_ETSY_HOST.setMaximumWidth(100)

                self.check_ETSY_PORT = gui.spin(
                        self.controlBox, self,
                        minv=1, maxv=65535,
                        value="ETSY_PORT",
                        label="(Etsy) Port")

                self.controlBox.resize(250, 250)
                self.check_ETSY_HOST.setAlignment(Qt.AlignTop)


            def setup_settings_box(self):
                # Settings box
                self.dummy = None
                self.settings_box = gui.widgetBox(self.controlBox, "Requests attributes")
                if not self.etsy_api_function_params:
                    self.noInputLabel = gui.widgetLabel(self.settings_box, "No route selected. Please select a function.")


            def setup_buttons_area(self):

                def showSetApiDialog():
                    nonlocal self
                    text, ok = QInputDialog.getText(self, "Set Etsy API token", "API Token: " ,QLineEdit.Password)
                    if ok:
                        if text:
                            self.ETSY_API_TOKEN = text
                            self.statusbarResLabel.setText("API successfully set")
                            self.sendRequestButton.setEnabled(True)
                            self.sendRequestButton.setText("Send request")

                            self.ETSY_API_CLIENT = EtsyOAuth2Client(
                                api_token=self.ETSY_API_TOKEN,
                                auto_close_browser=self.ETSY_AUTO_CLOSE_BROWSER,
                                auto_refresh_token=self.ETSY_AUTO_REFRESH_TOKEN,
                                auto_start_auth=self.ETSY_AUTO_START_AUTH,
                                verbose=self.ETSY_VERBOSE,
                                host=self.ETSY_HOST,
                                port=self.ETSY_PORT
                            )
                            self.ETSY_ROUTES = list(self.ETSY_API_CLIENT.get_api_routes())
                            if self.ETSY_ROUTES:
                                self.statusbarResLabel.setText("API routes successfully retrieved")
                            self.searchBox.clear()
                            self.searchBox.addItems([route[1] for route in self.ETSY_ROUTES])
                        else:
                            QtWidgets.QMessageBox.warning(self, "Error", "API token cannot be empty")

                self.sendRequestButton = gui.button(self.buttonsArea, self, "Please set token first")
                self.sendRequestButton.setEnabled(False)
                self.setTokenButton = gui.button(self.buttonsArea, self, "Set token", callback=showSetApiDialog)

            setup_control_box(self)
            setup_info_box(self)
            setup_settings_box(self)
            setup_buttons_area(self)




        def setup_content(self):
            self.mainAreaBox = gui.vBox(self.mainArea, True)

            def setup_search_box(self):
                self.searchBox = SearchBarComboBox(self.mainArea)
                def searchBoxCallback(index):
                    nonlocal self
                    self.dummy=None
                    self.CURR_SELECTED_METHOD_NAME, self.CURR_SELECTED_URI_VAL, \
                        self.CURR_SELECTED_METHOD, self.CURR_SELECTED_METHOD_ARGS, self.CURR_SELECTED_VERB\
                        = self.ETSY_ROUTES[index]

                    print(self.CURR_SELECTED_METHOD_NAME, self.CURR_SELECTED_URI_VAL,
                        self.CURR_SELECTED_METHOD, self.CURR_SELECTED_METHOD_ARGS)


                    layout = self.settings_box.layout()
                    for i in reversed(range(layout.count())):
                        item = layout.itemAt(i)
                        item.widget().close()

                    for arg_name in self.CURR_SELECTED_METHOD_ARGS:
                        if "{" + arg_name in self.CURR_SELECTED_URI_VAL + "}" \
                                and self.CURR_SELECTED_VERB == "GET":
                            gui.lineEdit(self.settings_box, self, value="dummy", label=arg_name)

                self.searchBox.currentIndexChanged.connect(searchBoxCallback)
                self.searchBox.show()

            def setup_table(self):
                self.tableWidget = QTableView(self.tableTab)
                self.tableWidget.setItemDelegate(EditableTableItemDelegate())
                self.tableWidget.setEditTriggers(self.tableWidget.CurrentChanged)

                self.tableWidget.resizeColumnsToContents()
                self.tableWidget.resizeRowsToContents()
                self.tableWidget.horizontalHeader().setStretchLastSection(True)
                self.tableWidget.verticalHeader().setStretchLastSection(True)

                self.tableWidget.setSizePolicy(3, 3)

                font = QtGui.QFont()
                font.setPointSize(10)
                self.tableWidget.setFont(font)

                # self.tableWidget.setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding)

                # Table model
                self.table_model = EditableTableModel()
                self.tableWidget.setModel(self.table_model)
                self.table_model.dataChanged.connect(self.data_changed)
                self.table_model.set_table(self.context_data)

            def setup_tree(self):
                self.treeWidget = tree_view = QTreeView(self.treeTab)  # Instantiate the View
                tree = {'Root': {"Level_1": {"Item_1": 1.10, "Item_2": 1.20, "Item_3": 1.30},
                                 "Level_2": {"SubLevel_1":
                                                 {"SubLevel_1_item1": 2.11, "SubLevel_1_Item2": 2.12,
                                                  "SubLevel_1_Item3": 2.13},
                                             "SubLevel_2":
                                                 {"SubLevel_2_Item1": 2.21, "SubLevel_2_Item2": 2.22,
                                                  "SubLevel_2_Item3": 2.23}},
                                 "Level_3": {"Item_1": 3.10, "Item_2": 3.20, "Item_3": 3.30}}}

                headers = ["Dictionary Keys", "Dictionary Values"]
                # Set the models
                model = DictTreeModel(headers, tree)
                tree_view.setModel(model)
                tree_view.expandAll()
                tree_view.resizeColumnToContents(0)

            def setup_tabs(self):
                def setup_table_tab(self):
                    self.tableTab = QtWidgets.QTabWidget()
                    self.tableTabBox = gui.vBox(self.tableTab, True)
                    self.tabWidget.addTab(self.tableTab, "Table tab")

                def setup_tree_tab(self):
                    self.treeTab = QtWidgets.QTabWidget()
                    self.treeTabBox = gui.vBox(self.treeTab, True)
                    self.tabWidget.addTab(self.treeTab, "Tree tab")

                self.tabWidget = QtWidgets.QTabWidget()
                self.tabWidget.setObjectName("tabWidget")

                setup_table_tab(self)
                setup_tree_tab(self)

                setup_table(self)
                setup_tree(self)

            setup_search_box(self)
            setup_tabs(self)
            self.mainAreaBox.layout().addWidget(self.searchBox)
            self.mainAreaBox.layout().addWidget(self.tabWidget)

        def setup_statusbar(self):
            def setup_http_status(self, status, color="green"):
                # Content box
                self.content_box = gui.vBox(self.mainArea, True, margin=0)

                self.statusbarResLabel = gui.widgetLabel(self.statusBar(), label="HTTP Status: " + status)
                if color: self.statusbarResLabel.setStyleSheet(f"QLabel {{ color : {color} }}")

            def setup_res_size_label(self, size, color=None):
                self.statusbarResLabel = gui.widgetLabel(self.statusBar(), label="Response size: " + size)
                if color: self.statusbarResLabel.setStyleSheet(f"QLabel {{ color : {color} }}")

            def setup_app_status_label(self, status, color=None):
                self.statusbarResLabel = gui.widgetLabel(self.statusBar(), label="Application Status: " + status)
                if color: self.statusbarResLabel.setStyleSheet(f"QLabel {{ color : {color} }}")


            setup_http_status(self, "200 OK")
            setup_res_size_label(self, "0.00 KB")
            setup_app_status_label(self, "Ready")

        setup_sidebar(self)
        setup_content(self)
        setup_statusbar(self)

    def resizeEvent(self, event):
        w = self.tableTab.width()
        h = self.tableTab.height()
        self.tableWidget.resize(w, h)
        self.treeWidget.resize(w, h)

        self.tableWidget.resizeColumnsToContents()
        self.tableWidget.resizeRowsToContents()

    @staticmethod
    def sizeHint():
        return QSize(800, 500)

    def openContext(self, data):
        super(OWCreateTable, self).openContext(data.domain if data else None)
        self.table_model.set_table(self.context_data)


if __name__ == "__main__":
    WidgetPreview(OWCreateTable).run()
