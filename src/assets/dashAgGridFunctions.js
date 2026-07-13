// Fonctions AG Grid exposées à Dash AG Grid via le namespace
// window.dashAgGridFunctions (cf. eventListeners de la grille du Tableau).
var dagfuncs = (window.dashAgGridFunctions = window.dashAgGridFunctions || {});

// Sources d'événements AG Grid qui ne correspondent PAS à une action de
// l'utilisateur : application programmatique d'une vue (props filterModel /
// columnState → source 'api') et initialisation de la grille. On les ignore ;
// toute autre source (ex. 'columnFilter', 'uiColumnSorted', 'toolPanelUi',
// 'columnMenu') est une modification volontaire de l'état par l'utilisateur.
var SHARE_PROGRAMMATIC_SOURCES = [
  "api",
  "gridInitializing",
  "gridOptionsChanged",
  "gridOptionsUpdated",
  "columnDefsUpdated",
];

// Masque le bloc « URL directe » (share-url-box) dès que l'utilisateur modifie
// filtre / tri / visibilité de colonne, en effaçant le store active-view.
// L'écho de l'application d'une vue (source 'api') est ignoré : plus de course
// d'ordonnancement ni de diff d'état fragile.
dagfuncs.hideShareOnUserAction = function (params) {
  var source = params && params.source;
  if (SHARE_PROGRAMMATIC_SOURCES.indexOf(source) !== -1) {
    return;
  }
  if (window.dash_clientside && window.dash_clientside.set_props) {
    window.dash_clientside.set_props("active-view", { data: null });
  }
};
