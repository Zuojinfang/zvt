# -*- coding: utf-8 -*-
import json
from typing import List

import dash_core_components as dcc
import dash_html_components as html
from dash import dash
from dash.dependencies import Input, Output, State

from zvdata.chart import Drawer
from zvdata.domain import global_providers, get_schemas, get_schema_by_name, get_schema_columns
from zvdata.normal_data import NormalData
from zvdata.reader import DataReader
from zvdata.utils.pd_utils import df_is_not_null
from zvdata.utils.time_utils import now_pd_timestamp, TIME_FORMAT_DAY
from zvt.api.common import get_important_column
from zvt.app import app
from zvt.settings import SAMPLE_STOCK_CODES

current_df = None

layout = html.Div(
    [
        html.Div(
            [
                # provider selector
                dcc.Dropdown(
                    id='provider-selector',
                    placeholder='select provider',
                    options=[{'label': provider, 'value': provider} for provider in
                             global_providers]),

                # schema selector
                dcc.Dropdown(id='schema-selector', placeholder='select schema'),

                # column selector
                html.Div(id='schema-column-selector-container', children=None),

                # selected properties
                dcc.Dropdown(
                    id='properties-selector',
                    options=[
                        {'label': 'undefined', 'value': 'undefined'}
                    ],
                    value='undefined',
                    multi=True
                ),

                # codes filter
                dcc.Input(id='input-code-filter', type='text', value=','.join(SAMPLE_STOCK_CODES),
                          style={'width': '400px'}),

                # time range filter
                dcc.DatePickerRange(
                    id='date-picker-range',
                    start_date='2009-01-01',
                    end_date=now_pd_timestamp(),
                    display_format=TIME_FORMAT_DAY
                ),

                # load data for table
                html.Button('load data', id='btn-load-data', n_clicks_timestamp=0),

                # table container
                html.Div(id='data-table-container', children=None),

                html.Div(id='table-type-label', children=None),

                html.Div(
                    [
                        html.Div([dcc.Dropdown(id='intent-selector')],
                                 style={'width': '50%', 'display': 'inline-block'}),
                        html.Div([dcc.Dropdown(id='chart-selector')],
                                 style={'width': '50%', 'display': 'inline-block'})
                    ]
                ),
                html.Div(id='chart-container', children=None)
            ])
    ]
)


@app.callback(
    Output('schema-selector', 'options'),
    [Input('provider-selector', 'value')])
def update_schema_selector(provider):
    if provider:
        return [{'label': schema.__name__, 'value': schema.__name__} for schema in
                get_schemas(provider=provider)]
    raise dash.exceptions.PreventUpdate()


@app.callback(
    Output('schema-column-selector-container', 'children'),
    [Input('schema-selector', 'value')],
    state=[State('provider-selector', 'value')])
def update_column_selector(schema_name, provider):
    if provider and schema_name:
        schema = get_schema_by_name(name=schema_name)
        cols = get_schema_columns(schema=schema)

        return dcc.Dropdown(
            id='schema-column-selector',
            options=[
                {'label': col, 'value': col} for col in cols
            ],
            value=get_important_column(schema_name=schema_name),
            multi=True
        )
    raise dash.exceptions.PreventUpdate()


@app.callback(
    [Output('properties-selector', 'options'),
     Output('properties-selector', 'value')],
    [Input('schema-column-selector', 'value')],
    state=[State('provider-selector', 'value'),
           State('schema-selector', 'value'),
           State('properties-selector', 'options'),
           State('properties-selector', 'value')])
def update_selected_properties(selected_cols, provider, schema_name, options, value):
    if selected_cols and provider and schema_name:
        current_options = options
        current_value = value

        added_labels = []
        added_values = []
        for col in selected_cols:
            added_labels.append(col)
            added_values.append(
                json.dumps({
                    'provider': provider,
                    'schema': schema_name,
                    'column': col
                }))

        added_options = [{'label': col, 'value': added_values[i]} for i, col in enumerate(added_labels)]

        if 'undefined' in value:
            current_options = []
            current_value = []

        current_options += added_options
        current_value += added_values

        return current_options, current_value

    raise dash.exceptions.PreventUpdate()


def properties_to_readers(properties, codes, start_date, end_date) -> List[DataReader]:
    provider_schema_map_cols = {}

    for prop in properties:
        provider = prop['provider']
        schema = prop['schema']
        key = (provider, schema)
        if key not in provider_schema_map_cols:
            provider_schema_map_cols[key] = []

        provider_schema_map_cols[key].append(prop['column'])

    readers = []
    for item, columns in provider_schema_map_cols.items():
        provider = item[0]
        schema = item[1]

        # TODO:better way to get time_field
        # if has_report_period(schema_name=schema):
        #     time_field = 'report_date'
        # else:
        #     time_field = 'timestamp'

        readers.append(DataReader(data_schema=get_schema_by_name(schema), provider=provider, codes=codes,
                                  columns=columns, start_timestamp=start_date, end_timestamp=end_date,
                                  time_field='timestamp'))

    return readers


@app.callback(
    [Output('data-table-container', 'children'),
     Output('table-type-label', 'children'),
     Output('intent-selector', 'options'),
     Output('intent-selector', 'value')],
    [Input('btn-load-data', 'n_clicks')],
    state=[State('properties-selector', 'value'),
           State('input-code-filter', 'value'),
           State('date-picker-range', 'start_date'),
           State('date-picker-range', 'end_date')])
def update_data_table(n_clicks, properties, codes: str, start_date, end_date):
    if n_clicks and properties:
        props = []
        for prop in properties:
            props.append(json.loads(prop))

        readers = properties_to_readers(properties=props, codes=codes, start_date=start_date,
                                        end_date=end_date)
        if readers:
            data_df = readers[0].data_df
            for reader in readers[1:]:
                if df_is_not_null(reader.data_df):
                    data_df = data_df.join(reader.data_df)

            global current_df
            current_df = data_df

            normal_data = NormalData(data_df)
            data_table = Drawer(data=normal_data).draw_data_table(id='data_table_content')

            intents = normal_data.get_intents()

            intent_options = [
                {'label': intent.value, 'value': intent.value} for intent in intents
            ]

            intent_value = intents[0].value

            return data_table, normal_data.get_table_type(), intent_options, intent_value


        else:
            return 'no data,please reselect!', '', [{'label': 'compare_self', 'value': 'compare_self'}], 'compare_self'

    raise dash.exceptions.PreventUpdate()


@app.callback(
    [Output('chart-selector', 'options'),
     Output('chart-selector', 'value')],
    [Input('intent-selector', 'value')])
def update_chart_selector(intent):
    if intent:
        charts = NormalData.get_charts_by_intent(intent=intent)
        options = [
            {'label': chart.value, 'value': chart.value} for chart in charts
        ]
        value = charts[0].value

        return options, value
    raise dash.exceptions.PreventUpdate()


operators_df = [['ge ', '>='],
                ['le ', '<='],
                ['lt ', '<'],
                ['gt ', '>'],
                ['ne ', '!='],
                ['eq ', '='],
                ['contains '],
                ['datestartswith ']]

operators_sql = [['>= ', '>='],
                 ['<= ', '<='],
                 ['< ', '<'],
                 ['> ', '>'],
                 ['!= ', '!='],
                 ['== ', '='],
                 ['contains '],
                 ['datestartswith ']]


def split_filter_part(filter_part, operators=operators_df):
    for operator_type in operators:
        for operator in operator_type:
            if operator in filter_part:
                name_part, value_part = filter_part.split(operator, 1)
                name = name_part[name_part.find('{') + 1: name_part.rfind('}')]

                value_part = value_part.strip()
                v0 = value_part[0]
                if (v0 == value_part[-1] and v0 in ("'", '"', '`')):
                    value = value_part[1: -1].replace('\\' + v0, v0)
                else:
                    try:
                        value = float(value_part)
                    except ValueError:
                        value = value_part

                # word operators need spaces after them in the filter string,
                # but we don't want these later
                return name, operator_type[0].strip(), value

    return [None] * 3


@app.callback(
    [Output('data_table_content', "data"),
     Output('chart-container', "children")],
    [Input('data_table_content', "page_current"),
     Input('data_table_content', "page_size"),
     Input('data_table_content', "sort_by"),
     Input('data_table_content', "filter_query"),
     Input('chart-selector', "value")])
def update_table_and_graph(page_current, page_size, sort_by, filter, chart):
    if chart:
        dff = current_df

        if filter:
            filtering_expressions = filter.split(' && ')
            for filter_part in filtering_expressions:
                col_name, operator, filter_value = split_filter_part(filter_part)

                if operator in ('eq', 'ne', 'lt', 'le', 'gt', 'ge'):
                    # these operators match pandas series operator method names
                    dff = dff.loc[getattr(dff[col_name], operator)(filter_value)]
                elif operator == 'contains':
                    dff = dff.loc[dff[col_name].str.contains(filter_value)]
                elif operator == 'datestartswith':
                    # this is a simplification of the front-end filtering logic,
                    # only works with complete fields in standard format
                    dff = dff.loc[dff[col_name].str.startswith(filter_value)]

        # if sort_by:
        #     dff = dff.sort_values(
        #         [col['entity_id'] for col in sort_by],
        #         ascending=[
        #             col['direction'] == 'asc'
        #             for col in sort_by
        #         ],
        #         inplace=False
        #     )

        graph_data, graph_layout = Drawer(NormalData(dff)).draw(chart=chart, render=None)

        table_data = dff.iloc[page_current * page_size: (page_current + 1) * page_size
                     ].to_dict('records')

        return table_data, \
               dcc.Graph(
                   id='chart-content',
                   figure={
                       'data': graph_data,
                       'layout': graph_layout
                   }
               )

    raise dash.exceptions.PreventUpdate()
