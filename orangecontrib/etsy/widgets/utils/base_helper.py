from collections import OrderedDict

import Orange
import numpy as np
import pandas
import pandas as pd
from Orange.data import DiscreteVariable, TimeVariable
from Orange.data import Domain, ContinuousVariable, DiscreteVariable
from sklearn.preprocessing import MultiLabelBinarizer


class BaseHelper:
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
