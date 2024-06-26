import json
import os
import sys
from collections import OrderedDict
from functools import partial

import Orange
import numpy as np
import pandas
import pandas as pd
from AnyQt.QtWidgets import QComboBox
from Orange.data import DiscreteVariable, TimeVariable
from Orange.data import Domain, ContinuousVariable, DiscreteVariable
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import Qt, pyqtSignal, QVariant, QSize
from PyQt5.QtWidgets import QCheckBox, QSpinBox, QDoubleSpinBox, QLineEdit, QLabel, QHBoxLayout, QVBoxLayout, \
    QTreeWidgetItem, QPushButton, QTreeWidget, QWidget, QHeaderView, QMessageBox
from sklearn.preprocessing import MultiLabelBinarizer

from orangecontrib.etsy.widgets.lib.menu_helpers import TaxonomyMenuButton


class WidgetsHelper:
    def __init__(self):
        # DATA_PATH = os.path.join(this_dir, "data", "./api_reference.json")
        self.api_reference_json_file = open(self.ETSSY_API_REFERENCE_FILE_PATH, encoding="utf-8")
        self.api_reference_json = json.load(self.api_reference_json_file)
        self.parameters = self.get_parameters()

    def create_domain(self, df):
        attrs = []
        newdf = pandas.DataFrame()
        for col in df.columns:
            val = df[col]
            _type = val.dtype
            if _type in [np.int64, np.float64, np.int32,
                         np.float32, np.int16, np.float16]:
                attr_val = ContinuousVariable(col)
            elif _type in [np.bool_, bool]:
                attr_val = DiscreteVariable(col, values=["False", "True"])
            elif _type in [np.datetime64]:
                attr_val = TimeVariable(col)
            elif _type in [object]:
                # self.logger.debug("Skipping obj column: ", col)
                pass
            # from Orange.data import Variable
            # attr_val = Variable(col)
            # attr_val = DiscreteVariable(np.array(col))
            # attrs.append(StringVariable(str(col)))
            else:
                attr_val = None
            if attr_val:
                newdf[col] = val
                attrs.append(attr_val)
        domain = Domain(attrs)
        return domain, newdf

    def pandas_to_orange(self, df):
        domain, attributes, metas = self.construct_domain(df)
        orange_table = Orange.data.Table.from_numpy(domain=domain, X=df[attributes].values, Y=None,
                                                    metas=df[metas].values, W=None)
        return orange_table

    def construct_domain(self, df):
        columns = OrderedDict(df.dtypes)
        attributes = OrderedDict()
        metas = OrderedDict()
        for name, dtype in columns.items():
            if issubclass(dtype.type, np.number):
                if len(df[name].unique()) >= 13 or issubclass(dtype.type, np.inexact) or (
                        df[name].max() > len(df[name].unique())):
                    attributes[name] = Orange.data.ContinuousVariable(name)
                else:
                    df[name] = df[name].astype(str)
                    attributes[name] = Orange.data.DiscreteVariable(name,
                                            values=sorted(df[name].unique().tolist()))
            else:
                metas[name] = Orange.data.StringVariable(name)

        domain = Orange.data.Domain(attributes=attributes.values(), metas=metas.values())
        return domain, list(attributes.keys()), list(metas.keys())

    def binarize_columns(self, df, remove_original_columns=False):
        mlb = MultiLabelBinarizer()
        # all_lists = lambda column: (column.sample(int(len(column) * 0.1)).apply(type).astype(str) == "<class 'list'>").all(0)
        any_lists = lambda column: (column.sample(int(len(column) * 0.1)).apply(type).astype(str) == "<class 'list'>").any(0)
        for column in df.columns:
            if any_lists(df[column]):
                try:
                    transformed_column = mlb.fit_transform(df[column])
                    transformed_column = pd.DataFrame(transformed_column,
                                                      columns=[column + "_" + str(x) for x in mlb.classes_])
                    df = pd.concat([df, transformed_column], axis=1)
                    if remove_original_columns:
                        df = df.drop(column, axis=1)
                except Exception as e:
                    warning_message = f"Could not flatten column (binarize_columns): {column} "
                    QMessageBox.warning(self, "Warning", warning_message + str(e), QMessageBox.Ok)
                    self.warning(warning_message + str(e))
        return df

    def clear_element(self, element):
        layout = element.layout()
        for i in reversed(range(layout.count())):
            item = layout.itemAt(i)
            widget = item.widget()
            if widget:
                widget.close()

    def get_parameters(self):
        parameters = {}
        # loop through paths
        for path in self.api_reference_json["paths"]:
            # loop through all items
            for item in self.api_reference_json["paths"][path]:
                # loop through all sub items
                for sub_item_name in self.api_reference_json["paths"][path][item]:
                    # get object
                    obj = self.api_reference_json["paths"][path][item][sub_item_name]
                    # check if sub_item_name is "parameters"
                    if sub_item_name == "parameters":
                        for parameter in obj:
                            parameters[parameter["name"]] = parameter
        return parameters

    def build_pyqt_element_from_parameter(self, parameter_name, callback):
        parameter = self.parameters.get(parameter_name)
        if not parameter:
            # self.logger.debug("Parameter not found in arguments documentation: ", parameter_name)
            return None, None
        schema = parameter["schema"]
        element = None

        if parameter_name == "taxonomy_id" and not self.TAXONOMY_ID_RAW:
            # if not hasattr(self, "taxonomy_button"):
            element = TaxonomyMenuButton(
                title="Taxonomy", results=self.ETSY_taxonomy_items["results"])
            element.objectNameChanged.connect(lambda text : callback(
                data=self.sender().taxonomy_id, widget=element, widget_name="taxonomy_id"))

        elif "enum" in schema:
            # create QComboBox
            enum = schema["enum"]
            element = QComboBox()
            element.addItems(enum)
            element.activated[str].connect(partial(callback, widget=element))

        elif schema["type"] == "boolean":
            # create QCheckBox
            element = QCheckBox()
            element.stateChanged.connect(partial(callback, widget=element))
        #
        # elif schema["type"] == "integer"\
        #         and not parameter["name"] in ["shop_id", "taxonomy_id"]:
        elif schema["type"] == "integer" \
                and not (parameter["name"] in ["shop_id", "taxonomy_id"]) \
                or (parameter["name"] == "taxonomy_id" and self.TAXONOMY_ID_RAW):
            # Code block to execute when the condition is True

            # Code block to execute when the condition is True

            # create QSpinBox
            element = QSpinBox()
            element.setReadOnly(False)

            minimum = schema["minimum"] if "minimum" in schema else -2147483648 #-sys.maxsize - 1
            maximum = schema["maximum"] if "maximum" in schema else  2147483647 #sys.maxsize -1

            element.setMinimum(minimum)
            element.setMaximum(maximum)

            default = schema.get("default", None)
            if default: element.setValue(default)

            # self.logger.debug("Parameter -->", parameter["name"])

            # element.textChanged.connect(partial(callback, widget=element))
            element.valueChanged.connect(partial(callback, widget=element))


        elif schema["type"] == "number" \
                and schema["format"] == "float":
            # create QDoubleSpinBox
            element = QDoubleSpinBox()
            element.setReadOnly(False)
            element.valueChanged.connect(partial(callback, widget=element))

        elif schema["type"] == "string":
            # create QLineEdit
            element = QLineEdit()
            element.setDragEnabled(True)
            element.setReadOnly(False)
            element.setPlaceholderText(parameter["name"])
            element.textChanged.connect(partial(callback, widget=element))
        else:
            # create QLineEdit
            element = QLineEdit()
            element.setDragEnabled(True)
            element.setReadOnly(False)
            element.setPlaceholderText(parameter["name"])
            element.textChanged.connect(partial(callback, widget=element))

        # set tooltip
        if "description" in parameter:
            element.setToolTip(parameter["description"])
        element.setObjectName(parameter["name"])
        return element, QLabel(parameter["name"])

    def build_element_with_label_layout(self, label_text, element, ret_all_elements=False):
        hbox = QHBoxLayout()
        label = QLabel(label_text)
        hbox.addWidget(label)
        hbox.addWidget(element)
        return hbox if not ret_all_elements else (hbox, label, element)

    def build_element_with_label(self, label_text, element):
        # el = QWidget()
        # el.setLayout(self.build_element_with_label_layout(label_text, element))
        # return el
        return self.layout_to_element(self.build_element_with_label_layout(label_text, element))


    def layout_to_element(self, layout):
        element = QWidget()
        element.setLayout(layout)
        return element

    def toggle_element_enabled(self, element):
        element.setEnabled(not element.isEnabled())
    def toggle_elements_enabled(self, elements):
        for element in elements:
            self.toggle_element_enabled(element)


class SetupHelper:
    def setup_arg_elements(self):
        for arg_name in self.CURR_SELECTED_METHOD_ARGS:
            parameter = self.parameters.get(arg_name)

            parent = self.required_parameters_box \
                        if (parameter["required"] if parameter else False) \
                            else self.optional_parameters_box

            def elementCallback(data, widget=None,widget_name=None):
                nonlocal self
                if not widget_name:
                    widget_name = widget.objectName()
                # self.logger.debug(widget_name)
                # self.logger.debug(self.ETSY_API_CLIENT_SEND_REQUEST_KWARGS)
                if widget_name == "limit" or widget_name == "offset":
                    pass # TODO: Check if this kwarg does not already exist
                self.ETSY_API_CLIENT_SEND_REQUEST_KWARGS[widget_name] = data

            element, label = self.build_pyqt_element_from_parameter(arg_name, elementCallback)

            # if name is offset or limit elements
            if arg_name == "offset":
                # save the values to an attribute
                self.offset_element = element
            if arg_name == "limit":
                # save the values to an attribute
                self.limit_element = element

            if element is not None and label is not None:
                parent.layout().addWidget(label)
                parent.layout().addWidget(element)


    def disable_qgroupbox_and_grayout_title(self, groupbox):
        groupbox.setEnabled(False)
        self.add_to_stylesheet(groupbox, "QGroupBox { color: gray; }")

    def enable_qgroupbox_and_color_title(self, groupbox, color="black"):
        groupbox.setEnabled(True)
        self.add_to_stylesheet(groupbox, "QGroupBox::title {color: " + color + ";}")

    def add_to_stylesheet(self, element, style):
        element.setStyleSheet(element.styleSheet() + style)


class ElementTreeWidget(QTreeWidget):
    def __init__(self, top_level_element=None, elements=None):
        super().__init__()

        # self.setStyleSheet("background-color: transparent; border: 0px;")

        # hide the background for the parent element only
        self.setStyleSheet("ElementTreeWidget{background-color: transparent; border: 0px;}")

        self.setHeaderHidden(True)
        # self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)


        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        # fit the tree widget to the content
        self.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.AdjustToContents)

        self.elements = elements
        self.top_level_element = top_level_element
        if self.top_level_element:
            self.addTopLevelItem(self.top_level_element)
            if elements:
                for element in self.elements:
                    self.add_element(element)

        # self.setStretchLastSection(False)
        # self.setSectionResizeMode(QHeaderView.ResizeToContents)

    # reimplement sizeHint to fit the content
    # def sizeHint(self):
    #     return QSize(self.sizeHintForColumn(0) + self.verticalScrollBar().sizeHint().width(),
    #                  self.sizeHintForRow(0) * self.topLevelItemCount())
    #
    # # reimplement minimumSizeHint to fit the content
    # def minimumSizeHint(self):
    #     return self.sizeHint()
    #
    # # reimplement resizeEvent to fit the content
    # def resizeEvent(self, event):
    #     self.resizeColumnToContents(0)
    #     super().resizeEvent(event)
    #





    def set_top_level_element(self, top_level_element):
        self.top_level_element = top_level_element
        self.topLevelElement = top_level_element
        self.topLevelItem = QTreeWidgetItem()
        self.addTopLevelItem(self.topLevelItem)
        self.setItemWidget(self.topLevelItem, 0, self.topLevelElement)
    def add_element(self, element):
        child_widget_item = QTreeWidgetItem()
        self.topLevelItem.addChild(child_widget_item)
        self.setItemWidget(child_widget_item, 0, element)

        # check if top level element is a checkbox and the element is a checkbox
        if isinstance(self.topLevelElement, QCheckBox) \
                and isinstance(element, QCheckBox):
            # check if the element is checked
            if element.isChecked():
                # set the top level element to tristate
                self.topLevelElement.setCheckState(Qt.PartiallyChecked)

    def resizeEvent(self, event):
        w = self.width()
        h = self.height()
        self.resize(w, h)
        self.resize(w, h)






