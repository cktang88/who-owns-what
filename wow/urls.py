from django.urls import path

from . import views

app_name = "wow"

urlpatterns = [
    path("address", views.address_query, name="address_query"),
    path(
        "address/wowza",
        views.address_query_with_portfolio_graph,
        name="address_query_with_portfolio_graph",
    ),
    path("address/aggregate", views.address_aggregate, name="address_aggregate"),
    path(
        "address/dap-aggregate",
        views.address_dap_aggregate,
        name="address_dap_aggregate",
    ),
    path(
        "address/dap-portfoliosize",
        views.address_dap_portfoliosize,
        name="address_dap_portfoliosize",
    ),
    path(
        "address/buildinginfo", views.address_buildinginfo, name="address_buildinginfo"
    ),
    path(
        "address/indicatorhistory",
        views.address_indicatorhistory,
        name="address_indicatorhistory",
    ),
    path("address/export", views.address_export, name="address_export"),
    path("address/latestdeed", views.address_latestdeed, name="address_latestdeed"),
]
