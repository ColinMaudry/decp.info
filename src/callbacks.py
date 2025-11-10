import polars as pl
from dash import dash_table, html

from utils import add_links_in_dict, format_montant, setup_table_columns


def get_top_org_table(data, org_type: str):
    dff = pl.DataFrame(data)
    if dff.height == 0:
        return html.Div()

    dff = dff.select(["uid", f"{org_type}_id", f"{org_type}_nom", "montant"])
    dff_nb = dff.group_by(f"{org_type}_id", f"{org_type}_nom").agg(
        pl.len().alias("Attributions"), pl.sum("montant").alias("montant")
    )
    dff_nb = dff_nb.sort(by="Attributions", descending=True)
    dff_nb = dff_nb.cast(pl.String)
    dff_nb = dff_nb.fill_null("")
    dff_nb = format_montant(dff_nb, column="montant")
    columns, tooltip = setup_table_columns(
        dff_nb, hideable=False, exclude=[f"{org_type}_id"]
    )
    data = dff_nb.to_dicts()
    data = add_links_in_dict(data, f"{org_type}")

    print(dff_nb)

    return dash_table.DataTable(
        data=data,
        markdown_options={"html": True},
        page_action="native",
        page_size=10,
        columns=columns,
        tooltip_header=tooltip,
    )
