import polars as pl
from dash import dash_table, html

from utils import add_links_in_dict, format_values, setup_table_columns


def get_top_org_table(data, org_type: str):
    dff = pl.DataFrame(data)
    if dff.height == 0:
        return html.Div()

    dff = dff.select(
        ["uid", f"{org_type}_id", f"{org_type}_nom", "distance", "montant"]
    )
    dff_nb = dff.group_by(f"{org_type}_id", f"{org_type}_nom", "distance").agg(
        pl.len().alias("Attributions"), pl.sum("montant").alias("montant")
    )
    dff_nb = dff_nb.sort(by="montant", descending=True)
    dff_nb = dff_nb.cast(pl.String)
    dff_nb = dff_nb.fill_null("")
    dff_nb = format_values(dff_nb)
    columns, tooltip = setup_table_columns(
        dff_nb, hideable=False, exclude=[f"{org_type}_id"]
    )
    data = dff_nb.to_dicts()
    data = add_links_in_dict(data, f"{org_type}")

    return dash_table.DataTable(
        data=data,
        markdown_options={"html": True},
        page_action="native",
        page_size=10,
        columns=columns,
        cell_selectable=False,
        tooltip_header=tooltip,
        style_cell_conditional=[
            {
                "if": {"column_id": "objet"},
                "minWidth": "350px",
                "textAlign": "left",
                "overflow": "hidden",
                "lineHeight": "14px",
                "whiteSpace": "normal",
                "fontSize": "85%",
            },
            {
                "if": {"column_id": "acheteur_nom"},
                "minWidth": "200px",
                "textAlign": "left",
                "overflow": "hidden",
                "lineHeight": "16px",
                # "fontSize": "85%",
                "whiteSpace": "normal",
            },
            {
                "if": {"column_id": "titulaire_nom"},
                "minWidth": "200px",
                "textAlign": "left",
                "overflow": "hidden",
                "lineHeight": "16px",
                "whiteSpace": "normal",
                # "fontSize": "85%",
            },
        ],
    )
