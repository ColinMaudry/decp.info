import polars as pl
from dash import html

from src.figures import DataTable
from utils import add_links_in_dict, format_values, setup_table_columns


def get_top_org_table(data, org_type: str):
    dff = pl.DataFrame(data, strict=False, infer_schema_length=5000)
    if dff.height == 0:
        return html.Div()

    dff = dff.select(
        ["uid", f"{org_type}_id", f"{org_type}_nom", "distance", "montant"]
    )
    dff_nb = dff.group_by(f"{org_type}_id", f"{org_type}_nom", "distance").agg(
        pl.len().alias("Attributions"), pl.sum("montant").alias("montant")
    )
    dff_nb = dff_nb.sort(by="montant", descending=True, nulls_last=True)
    dff_nb = dff_nb.cast(pl.String)
    dff_nb = dff_nb.fill_null("")
    dff_nb = format_values(dff_nb)
    columns, tooltip = setup_table_columns(
        dff_nb, hideable=False, exclude=[f"{org_type}_id"], new_columns=["Attributions"]
    )
    data = dff_nb.to_dicts()
    data = add_links_in_dict(data, f"{org_type}")

    return DataTable(
        dtid=f"top10_{org_type}",
        data=data,
        page_action="native",
        page_size=10,
        columns=columns,
        tooltip_header=tooltip,
    )
