import json
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
    QTreeWidgetItem, QPushButton, QTreeWidget, QWidget, QHeaderView
from sklearn.preprocessing import MultiLabelBinarizer


class WidgetsHelper:
    def __init__(self):
        self.api_reference_json_file = open("./data/api_reference.json", encoding="utf-8")
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
                print("Skipping obj column: ", col)
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
        all_lists = lambda column: (column.sample(100).apply(type).astype(str) == "<class 'list'>").all(0)
        any_lists = lambda column: (column.sample(100).apply(type).astype(str) == "<class 'list'>").any(0)

        for column in df.columns:
            if any_lists(df[column]):
                transformed_column = mlb.fit_transform(df[column])
                transformed_column = pd.DataFrame(transformed_column,
                                                  columns=[column + "_" + str(x) for x in mlb.classes_])
                df = pd.concat([df, transformed_column], axis=1)
                if remove_original_columns:
                    df = df.drop(column, axis=1)
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
        parameter = self.parameters[parameter_name]
        schema = parameter["schema"]
        element = None
        if "enum" in schema:
            # create QComboBox
            enum = schema["enum"]
            element = QComboBox()
            element.addItems(enum)
            element.activated[str].connect(partial(callback, widget=element))

        elif schema["type"] == "boolean":
            # create QCheckBox
            element = QCheckBox()
            element.stateChanged.connect(partial(callback, widget=element))

        elif schema["type"] == "integer"\
                and not parameter["name"] in ["shop_id"]:
            # create QSpinBox
            element = QSpinBox()
            element.setReadOnly(False)

            if "minimum" in schema:
                element.setMinimum(schema["minimum"])
            if "maximum" in schema:
                element.setMaximum(schema["maximum"])
            if "default" in schema:
                element.setValue(schema["default"])

            element.textChanged.connect(partial(callback, widget=element))


        elif schema["type"] == "number" \
                and schema["format"] == "float":
            # create QDoubleSpinBox
            element = QDoubleSpinBox()
            element.setReadOnly(False)
            element.textChanged.connect(partial(callback, widget=element))

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

    def build_element_with_label_layout(self, label_text, element):
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel(label_text))
        hbox.addWidget(element)
        return hbox

    def build_element_with_label(self, label_text, element):
        el = QWidget()
        el.setLayout(self.build_element_with_label_layout(label_text, element))
        return el

class ElementTreeWidget(QTreeWidget):
    def __init__(self, top_level_element=None, elements=None):
        super().__init__()

        # self.setStyleSheet("background-color: transparent; border: 0px;")

        # hide the background for the parent element only
        self.setStyleSheet("ElementTreeWidget{background-color: transparent; border: 0px;}")

        self.setHeaderHidden(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)


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






