import os
import pyodbc
import pandas as pd
import dash
from dash import dcc, html
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

SYNAPSE_SERVER = "synw-retail-credit-rc01-ondemand.sql.azuresynapse.net"
SYNAPSE_DB = "retail_credit"
GRADE_MAP = {1: "A", 2: "B", 3: "C", 4: "D", 5: "E", 6: "F", 7: "G"}


def get_connection():
    conn_str = (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server={SYNAPSE_SERVER};"
        f"Database={SYNAPSE_DB};"
        "Authentication=ActiveDirectoryMsi;"
    )
    return pyodbc.connect(conn_str)


def load_data():
    conn = get_connection()
    data = {}
    queries = {
        "portfolio":   "SELECT * FROM dbo.vw_portfolio_summary",
        "segment":     "SELECT * FROM dbo.vw_default_by_segment",
        "vintage":     "SELECT * FROM dbo.vw_vintage_curves",
        "performance": "SELECT * FROM dbo.vw_model_performance",
    }
    for key, sql in queries.items():
        data[key] = pd.read_sql(sql, conn)
    conn.close()

    # map grade_int to letter grade
    if "grade_int" in data["portfolio"].columns:
        data["portfolio"]["grade"] = data["portfolio"]["grade_int"].map(GRADE_MAP)
    if "grade_int" in data["segment"].columns:
        data["segment"]["grade"] = data["segment"]["grade_int"].map(GRADE_MAP)

    return data


# load on startup
print("Loading data from Synapse...")
data = load_data()
print("Data loaded.")

portfolio = data["portfolio"].sort_values("grade_int")
segment   = data["segment"]
vintage   = data["vintage"].sort_values("credit_age_months")
perf      = data["performance"].iloc[0]

# ── charts ────────────────────────────────────────────────────────────────────

def kpi_gauge(value, title, max_val=1.0, color="steelblue"):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=round(value * 100, 1),
        number={"suffix": "%"},
        title={"text": title},
        gauge={
            "axis": {"range": [0, max_val * 100]},
            "bar": {"color": color},
            "steps": [
                {"range": [0, max_val * 33], "color": "#e8f5e9"},
                {"range": [max_val * 33, max_val * 66], "color": "#fff9c4"},
                {"range": [max_val * 66, max_val * 100], "color": "#ffebee"},
            ],
        },
    ))
    fig.update_layout(height=220, margin=dict(t=40, b=10, l=20, r=20))
    return fig


def bar_loan_volume():
    fig = px.bar(
        portfolio, x="grade", y="total_loans",
        color="default_rate",
        color_continuous_scale="RdYlGn_r",
        labels={"total_loans": "Total Loans", "grade": "Grade", "default_rate": "Default Rate"},
        title="Loan Volume by Grade",
    )
    fig.update_layout(height=350)
    return fig


def heatmap_default():
    pivot = segment.pivot_table(
        index="grade", columns="term",
        values="default_rate", aggfunc="mean"
    )
    fig = px.imshow(
        pivot,
        color_continuous_scale="RdYlGn_r",
        labels={"color": "Default Rate"},
        title="Default Rate by Grade × Term",
        text_auto=".1%",
    )
    fig.update_layout(height=350)
    return fig


def line_vintage():
    fig = px.line(
        vintage, x="credit_age_months", y="default_rate",
        labels={"credit_age_months": "Credit Age (months)", "default_rate": "Default Rate"},
        title="Default Rate by Credit Age (Vintage Curve)",
    )
    fig.update_traces(line_color="steelblue")
    fig.update_layout(height=350, yaxis_tickformat=".1%")
    return fig


def bar_avg_int_rate():
    fig = px.bar(
        portfolio, x="grade", y="avg_int_rate",
        color="avg_int_rate",
        color_continuous_scale="Blues",
        labels={"avg_int_rate": "Avg Interest Rate (%)", "grade": "Grade"},
        title="Average Interest Rate by Grade",
    )
    fig.update_layout(height=350)
    return fig


def bar_predicted_vs_actual():
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Actual Defaults",
        x=["Portfolio"],
        y=[perf["actual_default_rate"] * 100],
        marker_color="tomato",
    ))
    fig.add_trace(go.Bar(
        name="Predicted Defaults",
        x=["Portfolio"],
        y=[perf["predicted_default_rate"] * 100],
        marker_color="steelblue",
    ))
    fig.update_layout(
        title="Actual vs Predicted Default Rate",
        yaxis_title="Default Rate (%)",
        barmode="group",
        height=350,
    )
    return fig


# ── layout ────────────────────────────────────────────────────────────────────

app = dash.Dash(__name__)
app.title = "Retail Credit Portfolio Analytics"

app.layout = html.Div(style={"fontFamily": "Arial, sans-serif", "backgroundColor": "#f5f5f5"}, children=[

    html.Div(style={"backgroundColor": "#1a237e", "padding": "20px 30px", "color": "white"}, children=[
        html.H1("Retail Credit Portfolio Analytics", style={"margin": 0}),
        html.P("LendingClub 2007–2018 · Azure ML · Synapse Serverless SQL", style={"margin": "5px 0 0", "opacity": 0.8}),
    ]),

    # KPI row
    html.Div(style={"display": "flex", "gap": "10px", "padding": "20px 30px 0"}, children=[
        html.Div(style={"flex": 1, "backgroundColor": "white", "borderRadius": "8px", "padding": "10px"}, children=[
            dcc.Graph(figure=kpi_gauge(perf["actual_default_rate"], "Actual Default Rate", color="tomato"))
        ]),
        html.Div(style={"flex": 1, "backgroundColor": "white", "borderRadius": "8px", "padding": "10px"}, children=[
            dcc.Graph(figure=kpi_gauge(perf["predicted_default_rate"], "Predicted Default Rate", color="steelblue"))
        ]),
        html.Div(style={"flex": 1, "backgroundColor": "white", "borderRadius": "8px", "padding": "10px"}, children=[
            dcc.Graph(figure=kpi_gauge(perf["avg_default_probability"], "Avg Default Probability", color="darkorange"))
        ]),
    ]),

    # row 2
    html.Div(style={"display": "flex", "gap": "10px", "padding": "10px 30px 0"}, children=[
        html.Div(style={"flex": 1, "backgroundColor": "white", "borderRadius": "8px", "padding": "10px"}, children=[
            dcc.Graph(figure=bar_loan_volume())
        ]),
        html.Div(style={"flex": 1, "backgroundColor": "white", "borderRadius": "8px", "padding": "10px"}, children=[
            dcc.Graph(figure=heatmap_default())
        ]),
    ]),

    # row 3
    html.Div(style={"display": "flex", "gap": "10px", "padding": "10px 30px 0"}, children=[
        html.Div(style={"flex": 1, "backgroundColor": "white", "borderRadius": "8px", "padding": "10px"}, children=[
            dcc.Graph(figure=line_vintage())
        ]),
        html.Div(style={"flex": 1, "backgroundColor": "white", "borderRadius": "8px", "padding": "10px"}, children=[
            dcc.Graph(figure=bar_avg_int_rate())
        ]),
    ]),

    # row 4
    html.Div(style={"display": "flex", "gap": "10px", "padding": "10px 30px 20px"}, children=[
        html.Div(style={"flex": 1, "backgroundColor": "white", "borderRadius": "8px", "padding": "10px"}, children=[
            dcc.Graph(figure=bar_predicted_vs_actual())
        ]),
        html.Div(style={"flex": 1, "backgroundColor": "white", "borderRadius": "8px", "padding": "10px"}, children=[
            html.H3("Dataset Summary", style={"paddingLeft": "10px", "color": "#1a237e"}),
            html.Table(style={"width": "100%", "padding": "10px"}, children=[
                html.Tr([html.Td("Total Loans Scored"), html.Td(f"{int(perf['total_scored']):,}", style={"fontWeight": "bold"})]),
                html.Tr([html.Td("Actual Defaults"), html.Td(f"{int(perf['total_actual_defaults']):,}", style={"fontWeight": "bold", "color": "tomato"})]),
                html.Tr([html.Td("Predicted Defaults"), html.Td(f"{int(perf['total_predicted_defaults']):,}", style={"fontWeight": "bold", "color": "steelblue"})]),
                html.Tr([html.Td("Actual Default Rate"), html.Td(f"{perf['actual_default_rate']:.2%}", style={"fontWeight": "bold"})]),
                html.Tr([html.Td("Predicted Default Rate"), html.Td(f"{perf['predicted_default_rate']:.2%}", style={"fontWeight": "bold"})]),
            ]),
        ]),
    ]),

])

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)