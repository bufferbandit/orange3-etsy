import copy
import json
import pprint
import re
import sys
import traceback
from functools import partial
from typing import Optional

import numpy as np
import pandas
import pandas as pd
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
from etsyv3.etsy_api import BadRequest, Unauthorised, NotFound, InternalError, Forbidden, Conflict

from orangecontrib.etsy.widgets.lib.etsy_api_client import EtsyOAuth2Client
from orangecontrib.etsy.widgets.lib.qjsonmodel import QJsonModel
from orangecontrib.etsy.widgets.lib.searchbar_helpers import SearchBarComboBox
from orangecontrib.etsy.widgets.lib.table_helpers import (
    TableHelpersBase, CreateTableContextHandler,
    EditableTableItemDelegate, EditableTableModel, PandasModel, DataFrameModel, DataFrameWidget, ObjTable)
from orangecontrib.etsy.widgets.lib.tabletest import PandasModel
from orangecontrib.etsy.widgets.lib.tree_helpers import DictTreeModel

DEFAULT_DATA = [[None] * 6 for y in range(20)]



class OrangeEtsyApiInterface(OWWidget):
    name = "Etsy API"
    description = "Orange widget for using the Etsy API and its data."
    icon = "icons/etsy_icon_round.svg"
    priority = 100
    keywords = ["Etsy", "API", "data", "web", "table"]

    DEBUG = True

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

    def default(self, *args, **kwargs):
        print("No function set yet.")
    etsy_client_send_request = default

    ETSY_API_CLIENT_SEND_REQUEST_ARGS = []
    ETSY_API_CLIENT_SEND_REQUEST_KWARGS = {}

    ETSY_ROUTES = []

    SELECT_RESULTS_ONLY_TABLE_VIEW = True
    SELECT_RESULTS_ONLY_OUTPUT = True

    ETSY_API_RESPONSE_DF = None
    ETSY_API_RESPONSE_DF_MODEL = None

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

                def toggle_check_SELECT_RESULTS_ONLY_callback():
                    nonlocal self
                    if self.ETSY_API_RESPONSE_DF is not None \
                            and self.ETSY_API_RESPONSE_DF_RESULTS  is not None:
                        self.populateData()
                self.toggle_check_SELECT_RESULTS_ONLY_callback = toggle_check_SELECT_RESULTS_ONLY_callback

                self.check_SELECT_RESULTS_ONLY_TABLE_VIEW = gui.checkBox(
                        self.controlBox, self, callback=self.toggle_check_SELECT_RESULTS_ONLY_callback,
                        value="SELECT_RESULTS_ONLY_TABLE_VIEW",
                        label="Select results only in table")

                self.check_SELECT_RESULTS_ONLY_OUTPUT = gui.checkBox(
                        self.controlBox, self, callback=self.toggle_check_SELECT_RESULTS_ONLY_callback,
                        value="SELECT_RESULTS_ONLY_OUTPUT",
                        label="Select results only in output")

                self.check_ETSY_HOST = gui.lineEdit(
                        self.controlBox, self,
                        value="ETSY_HOST",
                        label="(Etsy) Host")

                # self.check_ETSY_HOST.setMaximumWidth(100)


                self.check_ETSY_PORT = gui.spin(
                        self.controlBox, self,
                        minv=1, maxv=65535,
                        value="ETSY_PORT",
                        label="(Etsy) Port")
                    


                def populateData():
                    nonlocal self
                    if self.ETSY_API_RESPONSE is not None:
                        # show the button again
                        self.refresh_data_button.show()

                        # Populate tree view
                        tree_model = QJsonModel()
                        self.treeWidget.setModel(tree_model)
                        tree_model.load(self.ETSY_API_RESPONSE)

                        # Populate table view
                        self.ETSY_API_RESPONSE_DF = pd.DataFrame(self.ETSY_API_RESPONSE)
                        self.ETSY_API_RESPONSE_DF_RESULTS = pd.DataFrame(self.ETSY_API_RESPONSE["results"])

                        model = PandasModel(self.ETSY_API_RESPONSE_DF_RESULTS if self.SELECT_RESULTS_ONLY_TABLE_VIEW else self.ETSY_API_RESPONSE_DF)
                        self.tableWidget.setModel(model)

                        # self.Outputs.data.send(self.table)

                self.populateData = populateData
                self.refresh_data_button = gui.button(
                    self.controlBox, self, "Reload existing data",
                    callback=self.populateData)
                # hide button
                self.refresh_data_button.hide()

                # self.refresh_data_button.enabled = False


                self.controlBox.resize(250, 250)
                self.check_ETSY_HOST.setAlignment(Qt.AlignTop)

            def setup_settings_box(self):
                # Settings box
                self.settings_box = gui.widgetBox(self.controlBox, "Request attributes")
                if not self.etsy_api_function_params:
                    self.noInputLabel = gui.widgetLabel(self.settings_box, "No route selected. Please select a function.")


            def setup_buttons_area(self):

                def showSetApiDialog():
                    nonlocal self
                    text, ok = QInputDialog.getText(self, "Set Etsy API token", "API Token: ", QLineEdit.Password)
                    if ok:
                        if text:
                            self.ETSY_API_TOKEN = text
                            self.change_app_status_label("API successfully set")
                            self.setTokenButton.setText("Re-authenticate")
                            self.sendRequestButton.setEnabled(True)
                            self.sendRequestButton.setText("Send request")

                            def sendRequest():
                                nonlocal self
                                self.change_app_status_label("Sending request")
                                try:
                                    res = self.etsy_client_send_request(*self.ETSY_API_CLIENT_SEND_REQUEST_ARGS,
                                                                  **self.ETSY_API_CLIENT_SEND_REQUEST_KWARGS)
                                    self.ETSY_API_RESPONSE = res
                                    self.change_http_status_label("200 OK", color="green")


                                    # Populate tree view
                                    tree_model = QJsonModel()
                                    self.treeWidget.setModel(tree_model)
                                    tree_model.load(self.ETSY_API_RESPONSE)

                                    # Populate table view
                                    self.ETSY_API_RESPONSE_DF = pd.DataFrame(self.ETSY_API_RESPONSE)
                                    # model = DataFrameModel(self.ETSY_API_RESPONSE_DF)
                                    model = PandasModel(self.ETSY_API_RESPONSE_DF)
                                    self.tableWidget.setModel(model)


                                    # self.tableWidget.setModel(model)

                                    # table_model = DataFrameModel()
                                    # self.tableWidget.setModel(table_model)

                                    # table1 = Table(self.ETSY_API_RESPONSE)
                                    # table2 = Table(self.ETSY_API_RESPONSE_DF)
                                    pass

                                except BadRequest as e:
                                    self.change_http_status_label("400 Bad request", color="red")
                                except Unauthorised as e:
                                    self.change_http_status_label("401 Unauthorised", color="red")
                                except Forbidden as e:
                                    self.change_http_status_label("403 Forbidden", color="red")
                                except Conflict as e:
                                    self.change_http_status_label("409 Conflict", color="red")
                                except NotFound as e:
                                    self.change_http_status_label("404 Not found", color="red")
                                except InternalError as e:
                                    self.change_http_status_label("500 Internal server error", color="red")
                                except Exception as e:
                                    self.change_http_status_label("Unknown error while sending request", color="red")
                                    print(e)
                                    print(traceback.format_exc())

                            self.sendRequestButton.clicked.connect(sendRequest)

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
                            # method_name, uri_val, method, params, verb
                            self.ETSY_ROUTES_DICT_METHOD_NAME_KEY = { route[0]: route for route in self.ETSY_ROUTES }
                            self.ETSY_ROUTES_DICT_URL_KEY = { route[1]: route for route in self.ETSY_ROUTES }
                            if self.ETSY_ROUTES:
                                self.change_app_status_label("API routes successfully retrieved")
                            self.searchBox.clear()
                            for route in self.ETSY_ROUTES:
                                method_name, url, verb = route[0], route[1], route[4]
                                # Only using GET routes for now
                                if verb == "GET":
                                    self.searchBox.addItem(f"[{verb}] {method_name} -> {url}")

                        else:
                            QtWidgets.QMessageBox.warning(self, "Error", "API token cannot be empty")





                def debugFunc():
                    self.ETSY_API_RESPONSE = json.loads(open("data/json_res_1.json", encoding="utf8").read())
                    self.change_http_status_label("-100 DEBUGGING", color="orange")
                    self.populateData()
                self.debugFunc = debugFunc


                if self.DEBUG:
                    self.debugButton = gui.button(self.buttonsArea, self, "DBG data", callback=self.debugFunc)

                self.sendRequestButton = gui.button(self.buttonsArea, self, "Please authenticate")
                self.sendRequestButton.setEnabled(False)
                self.setTokenButton = gui.button(self.buttonsArea, self, "Authenticate", callback=showSetApiDialog)

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
                    bar_text = self.searchBox.currentText()#.split("->")[0].strip()
                    method_name_regex = re.compile(r"\[(GET|POST|PUT|DELETE)\] ([a-zA-Z0-9_]+) ->")
                    method_name_match = method_name_regex.match(bar_text)
                    method_name = method_name_match.group(2)

                    self.CURR_SELECTED_METHOD_NAME, self.CURR_SELECTED_URI_VAL, self.CURR_SELECTED_METHOD,\
                        self.CURR_SELECTED_METHOD_ARGS, self.CURR_SELECTED_VERB = self.ETSY_ROUTES_DICT_METHOD_NAME_KEY[method_name]

                    self.etsy_client_send_request = self.CURR_SELECTED_METHOD

                    # clear layout
                    layout = self.settings_box.layout()
                    for i in reversed(range(layout.count())):
                        item = layout.itemAt(i)
                        item.widget().close()

                    for arg_name in self.CURR_SELECTED_METHOD_ARGS:
                        if self.CURR_SELECTED_VERB == "GET" and ("{" + arg_name in self.CURR_SELECTED_URI_VAL + "}"):
                            self.settings_box.setTitle(" request attributes for: " + self.CURR_SELECTED_METHOD_NAME)
                            line_edit = QLineEdit(self.settings_box)
                            line_edit.setPlaceholderText(arg_name)
                            line_edit.setObjectName(arg_name)
                            self.settings_box.layout().addWidget(line_edit)

                            # Callback to handle input and setting it in kwargs
                            def lineEditCallback(data, widget=None):
                                nonlocal self
                                widget_name = widget.objectName()
                                self.ETSY_API_CLIENT_SEND_REQUEST_KWARGS[widget_name] = data
                            line_edit.textChanged.connect(partial(lineEditCallback, widget=line_edit))

                self.searchBox.currentIndexChanged.connect(searchBoxCallback)
                self.searchBox.show()

            def setup_table(self):
                # self.tableWidget = DataFrameWidget(self.tableTab)
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
                self.tableModel = EditableTableModel()
                self.tableWidget.setModel(self.tableModel)
                # self.tableModel.dataChanged.connect(self.data_changed)
                self.tableModel.set_table(self.context_data)

            def setup_tree(self):
                self.treeWidget = QTreeView(self.treeTab)  # Instantiate the View
                # headers = ["Dictionary Keys", "Dictionary Values"]
                # model = DictTreeModel(headers, tree)
                # tree_view.setModel(model)
                self.treeWidget.expandAll()
                self.treeWidget.resizeColumnToContents(0)

            def setup_tabs(self):
                def setup_table_tab(self):
                    self.tableTab = QtWidgets.QTabWidget()
                    self.tableTabBox = gui.vBox(self.tableTab, True)
                    self.tabWidget.addTab(self.tableTab, "Results table tab")

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
                self.statusbarStatusLabel = gui.widgetLabel(self.statusBar(), label="HTTP Status: " + status)
                if color: self.statusbarStatusLabel.setStyleSheet(f"QLabel {{ color : {color} }}")

            def setup_res_size_label(self, size, color=None):
                self.statusbarResLabel = gui.widgetLabel(self.statusBar(), label="Response size: " + size)
                if color: self.statusbarResLabel.setStyleSheet(f"QLabel {{ color : {color} }}")

            def setup_app_status_label(self, status, color=None):
                self.statusbarStatusLabel = gui.widgetLabel(self.statusBar(), label="Application Status: " + status)
                if color: self.statusbarStatusLabel.setStyleSheet(f"QLabel {{ color : {color} }}")

            def change_res_size_label(text, color=None):
                nonlocal self
                self.statusbarResLabel.setText("Application Status: " + text)
                if color: self.statusbarResLabel.setStyleSheet(f"QLabel {{ color : {color} }}")

            def change_app_status_label(text, color=None):
                nonlocal self
                self.statusbarStatusLabel.setText("Application Status: " + text)
                if color: self.statusbarStatusLabel.setStyleSheet(f"QLabel {{ color : {color} }}")

            def change_http_status_label(text, color=None):
                nonlocal self
                self.statusbarStatusLabel.setText("Application Status: " + text)
                if color: self.statusbarStatusLabel.setStyleSheet(f"QLabel {{ color : {color} }}")


            self.change_res_size_label = change_res_size_label
            self.change_app_status_label = change_app_status_label
            self.change_http_status_label = change_http_status_label

            setup_http_status(self, "No requests", "black")
            # setup_res_size_label(self, "0.00 KB")
            setup_app_status_label(self, "Ready")

        setup_sidebar(self)
        setup_content(self)
        setup_statusbar(self)

        # Exception hook that will be called when an exception is raised and log it to the status bar
        def exception_hook(exctype, value, traceback):
            nonlocal self
            self.change_app_status_label("Error: " + str(value), "red")
            sys.__excepthook__(exctype, value, traceback)

        # Set the exception hook
        sys.excepthook = exception_hook




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
        super(OrangeEtsyApiInterface, self).openContext(data.domain if data else None)
        self.table_model.set_table(self.context_data)


if __name__ == "__main__":
    WidgetPreview(OrangeEtsyApiInterface).run()
