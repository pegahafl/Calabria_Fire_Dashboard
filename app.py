# --- Imports ---
import geopandas as gpd
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output
import dash_bootstrap_components as dbc
import os

# --- Initialize app ---
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
app.title = "Calabria Wildfire Dashboard"
server = app.server  # Required for Render

# --- Load and prepare data ---
print("📂 Working directory:", os.getcwd())
print("📁 Files in /data:", os.listdir("data"))

gdf = gpd.read_file("data/calabria_fires_3035.shp")
gdf = gdf.to_crs(epsg=3857)  # Web Mercator for area calculation
gdf["geometry"] = gdf.geometry.apply(lambda g: g if g.is_valid else g.buffer(0))
gdf["area_ha"] = gdf.geometry.area / 10_000  # m² to hectares

# 🔍 Clean and format
gdf["date"] = pd.to_datetime(gdf["FIREDATE"], errors="coerce")
gdf.dropna(subset=["date", "area_ha"], inplace=True)
gdf["year"] = gdf["date"].dt.year
gdf["month"] = gdf["date"].dt.month
gdf["year_month"] = gdf["date"].dt.to_period("M").astype(str)
gdf["season"] = gdf["month"].apply(lambda m: "Summer" if 5 <= m <= 10 else "Winter")
gdf["size"] = gdf["area_ha"].apply(lambda a: "Big" if a > 100 else "Small")

# --- App Layout ---
app.layout = dbc.Container([
    html.H2("🔥 Calabria Wildfire Explorer", className="text-center mt-4 mb-3"),
    dcc.Tabs([
        dcc.Tab(label="📊 Dashboard", children=[
            dbc.Row([
                dbc.Col([
                    html.Label("Year Range:"),
                    dcc.RangeSlider(
                        min=gdf["year"].min(), max=gdf["year"].max(), step=1,
                        value=[gdf["year"].min(), gdf["year"].max()],
                        marks={int(y): str(y) for y in sorted(gdf["year"].unique())},
                        id="year-slider"
                    )
                ], md=12)
            ], className="mb-4"),

            dbc.Row([
                dbc.Col(dcc.Graph(id="timeseries-chart"), md=6),
                dbc.Col(dcc.Graph(id="map-chart"), md=6)
            ]),

            html.Div(id="summary-box", className="mt-3")
        ]),
        dcc.Tab(label="🔘 Circle Matrix Grid", children=[
            dcc.Graph(id="circle-matrix", figure=go.Figure(
                layout=dict(title="🧪 Placeholder – Circle Matrix Grid")
            ))
        ])
    ])
], fluid=True)

# --- Callbacks ---
@app.callback(
    Output("timeseries-chart", "figure"),
    Output("map-chart", "figure"),
    Output("summary-box", "children"),
    Input("year-slider", "value")
)
def update_dashboard(year_range):
    df = gdf[(gdf["year"] >= year_range[0]) & (gdf["year"] <= year_range[1])].copy()

    # 📈 Time Series
    ts = df.groupby(["year", "month"]).agg(area=("area_ha", "sum")).reset_index()
    ts["month_name"] = pd.to_datetime(ts["month"], format="%m").dt.strftime("%b")
    month_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    ts["month_name"] = pd.Categorical(ts["month_name"], categories=month_order, ordered=True)
    ts = ts.sort_values(["year", "month"])

    fig1 = px.line(ts, x="month_name", y="area", color="year", markers=True,
                   title="🔥 Burned Area by Month (EFFIS2000_2025)")
    fig1.update_yaxes(range=[0, 50000])
    fig1.update_layout(
        xaxis=dict(categoryorder='array', categoryarray=month_order),
        shapes=[
            dict(type="rect", xref="x", yref="paper", x0="Jan", x1="May", y0=0, y1=1,
                 fillcolor="LightBlue", opacity=0.3, layer="below"),
            dict(type="rect", xref="x", yref="paper", x0="May", x1="Oct", y0=0, y1=1,
                 fillcolor="LightPink", opacity=0.3, layer="below"),
            dict(type="rect", xref="x", yref="paper", x0="Oct", x1="Dec", y0=0, y1=1,
                 fillcolor="LightBlue", opacity=0.3, layer="below")
        ]
    )
    fig1.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(size=10, color="LightPink"), name="Summer (May–Oct)"))
    fig1.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(size=10, color="LightBlue"), name="Winter (Nov–Apr)"))

    # 🗺️ Map
    gdf_wgs = df.to_crs(epsg=4326)
    fig2 = px.scatter_mapbox(
        gdf_wgs,
        lat=gdf_wgs.geometry.centroid.y,
        lon=gdf_wgs.geometry.centroid.x,
        size="area_ha", color="season", zoom=7,
        hover_data=["year", "area_ha"], mapbox_style="carto-positron",
        title="🗺️ Fire Locations"
    )

    # 📦 Summary
    total_fires = len(df)
    total_area = df["area_ha"].sum()
    peak_year_by_fires = df["year"].value_counts().idxmax()
    peak_fires_count = df["year"].value_counts().max()
    peak_year_by_area = df.groupby("year")["area_ha"].sum().idxmax()
    peak_area_value = df.groupby("year")["area_ha"].sum().max()

    summary = f"""
    🔥 Total Fires: {total_fires:,} 🌍 Burned Area: {total_area:,.0f} ha  
    🗓️ Peak Year by # of Fires: {peak_year_by_fires} ({peak_fires_count} fires)  
    🗓️ Peak Year by Burned Area: {peak_year_by_area} ({peak_area_value:,.0f} ha)
    """

    return fig1, fig2, html.Pre(summary)

# --- Run app locally ---

@app.callback(Output("circle-matrix", "figure"), Input("year-slider", "value"))
def circle_matrix(year_range):
    df = gdf[(gdf["year"] >= year_range[0]) & (gdf["year"] <= year_range[1])]
    all_months = pd.DataFrame({"month": list(range(1, 13)), "key": 1})
    all_years = pd.DataFrame({"year": list(range(year_range[0], year_range[1] + 1)), "key": 1})
    full_grid = pd.merge(all_years, all_months, on="key").drop("key", axis=1)
    grouped = df.groupby(["year", "month"]).agg(count=("area_ha", "count"), area=("area_ha", "sum")).reset_index()
    grid = pd.merge(full_grid, grouped, on=["year", "month"], how="left").fillna(0)
    max_area = grid["area"].max()
    max_count = grid["count"].max()
    grid["radius"] = np.sqrt(grid["area"] / max_area) * 40 if max_area else 1
    grid["color_scale"] = grid["count"] / max_count if max_count else 0

    fig = px.scatter(
        grid, x="month", y="year", size="radius", color="color_scale",
        color_continuous_scale="YlOrRd", size_max=40,
        range_color=(0, 1),
        labels={"month": "Month", "year": "Year", "color_scale": "Relative Fire Count<br>(normalized to 0–1)"},
        title="🔘 Circle Matrix: Burned Area & Fire Count"
    )
    fig.update_layout(
        yaxis=dict(autorange="reversed"),
        xaxis=dict(tickmode="array", tickvals=list(range(1, 13)), ticktext=[
            "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
        ])
    )
    return fig

if __name__ == "__main__":
    app.run_server(debug=True)
