from datasette import hookimpl

@hookimpl
def menu_links(datasette, actor):
    return [
        {"href": "https://teamopendata.org/t/decp-info-les-donnees-de-la-commande-publique-pour-tous-questions-reponses-discussions/2948", "label": "Présentation / FAQ"},
        {"href": "https://github.com/ColinMaudry/decp-table-schema/#documentation-du-sch%C3%A9ma", "label": "Documentation des champs"},
        {"href": "https://github.com/ColinMaudry/decp.info", "label": "Code source"},
        {"href": "/versions", "label": "Notes de version"},
        {"href": "/inscription", "label": "Lettre d'information"},
        {"href": "/mentions-legales", "label": "Mentions légales"}
    ]
