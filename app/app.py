import os
import pyodbc
import pandas as pd
import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go

SYNAPSE_SERVER = "synw-retail-credit-rc01-ondemand.sql.azuresynapse.net"
SYNAPSE_DB     = "retail_credit"
GRADE_MAP      = {1: "A", 2: "B", 3: "C", 4: "D", 5: "E", 6: "F", 7: "G"}


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
    queries = {
        "portfolio":   "SELECT * FROM dbo.vw_portfolio_summary",
        "segment":     "SELECT * FROM dbo.vw_default_by_segment",
        "vintage":     "SELECT * FROM dbo.vw_vintage_curves",
        "performance": "SELECT * FROM dbo.vw_model_performance",
        "states":      "SELECT * FROM dbo.vw_loans_by_state",
        "int_rates":   "SELECT grade_int, int_rate FROM dbo.scored_predictions WHERE int_rate IS NOT NULL",
    }
    data = {}
    for key, sql in queries.items():
        try:
            data[key] = pd.read_sql(sql, conn)
        except Exception as e:
            print(f"Warning: could not load {key}: {e}")
            data[key] = pd.DataFrame()
    conn.close()

    for key in ["portfolio", "segment"]:
        if "grade_int" in data.get(key, pd.DataFrame()).columns:
            data[key]["grade"] = data[key]["grade_int"].map(GRADE_MAP)
    if "grade_int" in data.get("int_rates", pd.DataFrame()).columns:
        data["int_rates"]["grade"] = data["int_rates"]["grade_int"].map(GRADE_MAP)

    return data


print("Loading data from Synapse...")
data       = load_data()
portfolio  = data["portfolio"].sort_values("grade_int")
segment    = data["segment"]
vintage    = data["vintage"].sort_values("credit_age_months")
perf       = data["performance"].iloc[0]
states     = data["states"]
int_rates  = data["int_rates"]
ALL_GRADES = sorted(portfolio["grade"].dropna().unique().tolist())
print("Data loaded.")


# ── chart helpers ─────────────────────────────────────────────────────────────

def kpi_gauge(value, title, color="steelblue"):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=round(value * 100, 1),
        number={"suffix": "%", "font": {"size": 28}},
        title={"text": title, "font": {"size": 12}},
        gauge={
            "axis": {"range": [0, 50]},
            "bar": {"color": color},
            "steps": [
                {"range": [0, 15],  "color": "#e8f5e9"},
                {"range": [15, 30], "color": "#fff9c4"},
                {"range": [30, 50], "color": "#ffebee"},
            ],
        },
    ))
    fig.update_layout(height=190, margin=dict(t=40, b=0, l=10, r=10))
    return fig


def fig_loan_volume(df, selected=None):
    if df.empty:
        return go.Figure()
    fig = px.bar(
        portfolio[portfolio["grade"].isin(ALL_GRADES)].sort_values("grade_int"),
        x="grade", y="total_loans",
        color="default_rate", color_continuous_scale="RdYlGn_r",
        title="Loan Volume by Grade  <i>(click bar to cross-filter)</i>",
        labels={"total_loans": "Total Loans", "grade": "Grade", "default_rate": "Default Rate"},
    )
    if selected and len(selected) < len(ALL_GRADES):
        opacities = [1.0 if g in selected else 0.25 for g in portfolio["grade"].sort_values().unique()]
        fig.update_traces(marker_opacity=opacities)
    fig.update_layout(height=300, margin=dict(t=40, b=20, l=10, r=10))
    return fig


def fig_heatmap(df):
    if df.empty or "term" not in df.columns:
        return go.Figure()
    pivot = df.pivot_table(index="grade", columns="term", values="default_rate", aggfunc="mean")
    fig = px.imshow(
        pivot, color_continuous_scale="RdYlGn_r",
        title="Default Rate: Grade × Term  <i>(click row to filter grade)</i>",
        labels={"color": "Default Rate"},
        text_auto=".1%",
    )
    fig.update_layout(height=300, margin=dict(t=40, b=20, l=10, r=10))
    return fig


def fig_vintage():
    fig = px.line(
        vintage, x="credit_age_months", y="default_rate",
        title="Vintage Curve — Default Rate by Credit Age",
        labels={"credit_age_months": "Credit Age (months)", "default_rate": "Default Rate"},
    )
    fig.update_traces(line_color="steelblue", line_width=2)
    fig.update_layout(height=300, yaxis_tickformat=".1%", margin=dict(t=40, b=20, l=10, r=10))
    return fig


def fig_int_rate(df, selected=None):
    if df.empty:
        return go.Figure()
    base = portfolio[portfolio["grade"].isin(ALL_GRADES)].sort_values("grade_int")
    fig = px.bar(
        base, x="grade", y="avg_int_rate",
        color="avg_int_rate", color_continuous_scale="Blues",
        title="Avg Interest Rate by Grade  <i>(click bar to cross-filter)</i>",
        labels={"avg_int_rate": "Avg Interest Rate (%)", "grade": "Grade"},
    )
    if selected and len(selected) < len(ALL_GRADES):
        opacities = [1.0 if g in selected else 0.25 for g in base["grade"]]
        fig.update_traces(marker_opacity=opacities)
    fig.update_layout(height=300, margin=dict(t=40, b=20, l=10, r=10))
    return fig


def fig_actual_vs_predicted():
    fig = go.Figure([
        go.Bar(name="Actual",    x=["Portfolio"], y=[perf["actual_default_rate"] * 100],    marker_color="tomato"),
        go.Bar(name="Predicted", x=["Portfolio"], y=[perf["predicted_default_rate"] * 100], marker_color="steelblue"),
    ])
    fig.update_layout(
        title="Actual vs Predicted Default Rate",
        yaxis_title="Default Rate (%)",
        barmode="group", height=300,
        margin=dict(t=40, b=20, l=10, r=10),
    )
    return fig


def fig_choropleth(selected_state=None):
    if states.empty:
        return go.Figure().update_layout(title="Loan Volume by State (no data)")
    if selected_state:
        row = states[states["addr_state"] == selected_state]
        if not row.empty:
            r = row.iloc[0]
            title = (f"<b>{selected_state}</b> — {int(r['total_loans']):,} loans · "
                     f"${int(r['total_loan_amnt']):,} total · "
                     f"${int(r['avg_annual_inc']):,.0f} avg income "
                     f" <i>(click again to reset)</i>")
        else:
            title = "Loan Volume by State"
    else:
        title = "Loan Volume by State  <i>(click a state to highlight)</i>"
    fig = px.choropleth(
        states, locations="addr_state", locationmode="USA-states",
        color="total_loans", scope="usa",
        color_continuous_scale="Blues",
        title=title,
        labels={"total_loans": "Total Loans", "addr_state": "State",
                "total_loan_amnt": "Total Loan Amount", "avg_annual_inc": "Avg Annual Income"},
        hover_data={"total_loan_amnt": ":,.0f", "avg_annual_inc": ":,.0f"},
    )
    if selected_state:
        fig.add_trace(go.Choropleth(
            locations=[selected_state], z=[1],
            locationmode="USA-states",
            colorscale=[[0, "rgba(220,50,0,0.55)"], [1, "rgba(220,50,0,0.55)"]],
            showscale=False, hoverinfo="skip",
        ))
    fig.update_layout(height=380, margin=dict(t=50, b=10, l=10, r=10))
    return fig


def fig_violin(selected_grades):
    if int_rates.empty:
        return go.Figure().update_layout(title="Interest Rate Distribution (no data)")
    df = int_rates[int_rates["grade"].isin(selected_grades)] if selected_grades else int_rates
    fig = px.violin(
        df, x="grade", y="int_rate", box=True, points=False,
        color="grade", title="Interest Rate Distribution by Grade  <i>(click to filter)</i>",
        labels={"int_rate": "Interest Rate (%)", "grade": "Grade"},
        category_orders={"grade": ALL_GRADES},
    )
    fig.update_layout(height=320, showlegend=False, margin=dict(t=40, b=20, l=10, r=10))
    return fig


def fig_sankey(df):
    if df.empty:
        return go.Figure().update_layout(title="Loan Flow (no data)")
    grades = df["grade"].tolist()
    n      = len(grades)
    labels = ["All Loans"] + grades + ["Default", "Performing"]
    node_colors = (
        ["#1a237e"]
        + ["#4CAF50","#8BC34A","#FFEB3B","#FF9800","#F44336","#C62828","#880E4F"][:n]
        + ["tomato", "steelblue"]
    )
    sources, targets, values = [], [], []
    for i, (_, row) in enumerate(df.iterrows()):
        total    = int(row["total_loans"])
        defaults = int(total * row["default_rate"])
        sources += [0,     i+1,     i+1]
        targets += [i+1,   n+1,     n+2]
        values  += [total, defaults, total - defaults]
    fig = go.Figure(go.Sankey(
        node=dict(label=labels, color=node_colors, pad=12, thickness=16),
        link=dict(source=sources, target=targets, value=values),
    ))
    fig.update_layout(title="Loan Flow: Portfolio → Grade → Outcome", height=360,
                      margin=dict(t=40, b=10, l=10, r=10))
    return fig


# ── layout ────────────────────────────────────────────────────────────────────

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)
app.title = "Retail Credit Portfolio Analytics"

CARD = {"className": "shadow-sm mb-3 h-100"}
CFG  = {"responsive": True}

grade_opts = [{"label": f" {g}", "value": g} for g in ALL_GRADES]

app.layout = dbc.Container(fluid=True, style={"backgroundColor": "#f5f5f5", "padding": "0"}, children=[

    # ── header ───────────────────────────────────────────────────────────────
    html.Div(
        style={"backgroundColor": "#1a237e", "padding": "16px 24px", "color": "white", "marginBottom": "16px"},
        children=[
            html.H1("Retail Credit Portfolio Analytics",
                    style={"margin": 0, "fontSize": "clamp(16px, 4vw, 26px)"}),
            html.P("LendingClub 2007–2018 · Azure ML · Synapse Serverless SQL",
                   style={"margin": "4px 0 0", "opacity": 0.75, "fontSize": "clamp(11px, 2vw, 13px)"}),
        ],
    ),

    dbc.Container(fluid=True, style={"padding": "0 16px"}, children=[

        # ── filters ──────────────────────────────────────────────────────────
        dbc.Card(**CARD, children=[
            dbc.CardBody([
                dbc.Row(align="center", children=[
                    dbc.Col(html.H6("Filter by Loan Grade", className="mb-0 text-primary"), xs=12, md="auto"),
                    dbc.Col(
                        dcc.Checklist(
                            id="grade-filter",
                            options=grade_opts,
                            value=ALL_GRADES,
                            inline=True,
                            inputStyle={"marginRight": "4px"},
                            labelStyle={"marginRight": "14px", "fontSize": "13px"},
                        ),
                        xs=12, md=True,
                    ),
                    dbc.Col(
                        dbc.Button("Reset", id="reset-btn", color="outline-secondary", size="sm"),
                        xs=12, md="auto",
                    ),
                ]),
            ])
        ]),

        # ── KPI gauges ───────────────────────────────────────────────────────
        dbc.Row(className="mb-1", children=[
            dbc.Col(dbc.Card(**CARD, children=[dbc.CardBody(className="p-2", children=
                dcc.Graph(figure=kpi_gauge(perf["actual_default_rate"],    "Actual Default Rate",    "tomato"),      config=CFG)
            )]), xs=12, sm=4),
            dbc.Col(dbc.Card(**CARD, children=[dbc.CardBody(className="p-2", children=
                dcc.Graph(figure=kpi_gauge(perf["predicted_default_rate"], "Predicted Default Rate", "steelblue"),   config=CFG)
            )]), xs=12, sm=4),
            dbc.Col(dbc.Card(**CARD, children=[dbc.CardBody(className="p-2", children=
                dcc.Graph(figure=kpi_gauge(perf["avg_default_probability"], "Avg Default Probability","darkorange"),  config=CFG)
            )]), xs=12, sm=4),
        ]),

        # ── row 2: volume + heatmap + vintage ────────────────────────────────
        dbc.Row(children=[
            dbc.Col(dbc.Card(**CARD, children=[dbc.CardBody(dcc.Graph(id="fig-loan-volume", config=CFG))]), xs=12, md=4),
            dbc.Col(dbc.Card(**CARD, children=[dbc.CardBody(dcc.Graph(id="fig-heatmap",     config=CFG))]), xs=12, md=4),
            dbc.Col(dbc.Card(**CARD, children=[dbc.CardBody(dcc.Graph(figure=fig_vintage(),  config=CFG))]), xs=12, md=4),
        ]),

        # ── row 3: interest rate + actual vs predicted + summary ──────────────
        dbc.Row(children=[
            dbc.Col(dbc.Card(**CARD, children=[dbc.CardBody(dcc.Graph(id="fig-int-rate", config=CFG))]), xs=12, md=4),
            dbc.Col(dbc.Card(**CARD, children=[dbc.CardBody(dcc.Graph(figure=fig_actual_vs_predicted(), config=CFG))]), xs=12, md=4),
            dbc.Col(dbc.Card(**CARD, children=[dbc.CardBody([
                html.H5("Dataset Summary", className="text-primary mb-3"),
                dbc.Table([
                    html.Tbody([
                        html.Tr([html.Td("Total Loans Scored"),    html.Td(f"{int(perf['total_scored']):,}",               className="fw-bold text-end")]),
                        html.Tr([html.Td("Actual Defaults"),       html.Td(f"{int(perf['total_actual_defaults']):,}",      className="fw-bold text-end text-danger")]),
                        html.Tr([html.Td("Predicted Defaults"),    html.Td(f"{int(perf['total_predicted_defaults']):,}",   className="fw-bold text-end text-primary")]),
                        html.Tr([html.Td("Actual Default Rate"),   html.Td(f"{perf['actual_default_rate']:.2%}",           className="fw-bold text-end")]),
                        html.Tr([html.Td("Predicted Default Rate"),html.Td(f"{perf['predicted_default_rate']:.2%}",        className="fw-bold text-end")]),
                    ])
                ], borderless=True, size="sm"),
            ])]), xs=12, md=4),
        ]),

        # ── row 4: choropleth (full width) ────────────────────────────────────
        dbc.Row(children=[
            dcc.Store(id="selected-state", data=None),
        dbc.Col(dbc.Card(**CARD, children=[dbc.CardBody(dcc.Graph(id="fig-choropleth", figure=fig_choropleth(), config=CFG))]), xs=12),
        ]),

        # ── row 5: violin + sankey ────────────────────────────────────────────
        dbc.Row(className="mb-4", children=[
            dbc.Col(dbc.Card(**CARD, children=[dbc.CardBody(dcc.Graph(id="fig-violin", config=CFG))]), xs=12, md=6),
            dbc.Col(dbc.Card(**CARD, children=[dbc.CardBody(dcc.Graph(id="fig-sankey", config=CFG))]), xs=12, md=6),
        ]),

    ]),
])


# ── callbacks ─────────────────────────────────────────────────────────────────

@app.callback(
    Output("grade-filter", "value"),
    Input("reset-btn",       "n_clicks"),
    Input("fig-loan-volume", "clickData"),
    Input("fig-int-rate",    "clickData"),
    State("grade-filter", "value"),
    prevent_initial_call=True,
)
def handle_grade_selection(_, vol_click, rate_click, current):
    trigger = dash.callback_context.triggered[0]["prop_id"].split(".")[0]
    if trigger == "reset-btn":
        return ALL_GRADES
    click_data = vol_click if trigger == "fig-loan-volume" else rate_click
    if not click_data or not click_data.get("points"):
        return current or ALL_GRADES
    clicked_grade = click_data["points"][0]["x"]
    if current == [clicked_grade]:
        return ALL_GRADES
    return [clicked_grade]


@app.callback(
    Output("fig-loan-volume", "figure"),
    Output("fig-heatmap",     "figure"),
    Output("fig-int-rate",    "figure"),
    Output("fig-violin",      "figure"),
    Output("fig-sankey",      "figure"),
    Input("grade-filter", "value"),
)
def update_charts(selected):
    if not selected:
        selected = ALL_GRADES

    p = portfolio[portfolio["grade"].isin(selected)].copy()
    s = segment[segment["grade"].isin(selected)].copy() if "grade" in segment.columns else segment

    return (
        fig_loan_volume(p, selected),
        fig_heatmap(s),
        fig_int_rate(p, selected),
        fig_violin(selected),
        fig_sankey(p),
    )


@app.callback(
    Output("selected-state", "data"),
    Input("fig-choropleth", "clickData"),
    State("selected-state", "data"),
    prevent_initial_call=True,
)
def handle_state_click(click_data, current):
    if not click_data:
        return None
    clicked = click_data["points"][0]["location"]
    return None if current == clicked else clicked


@app.callback(
    Output("fig-choropleth", "figure"),
    Input("selected-state", "data"),
)
def update_choropleth(selected_state):
    return fig_choropleth(selected_state)


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)
