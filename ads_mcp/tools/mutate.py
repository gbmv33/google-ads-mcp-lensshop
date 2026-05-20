# LensShop customization — Google Ads write operations via MCP
#
# Adds four mutation tools not present in the upstream package:
#   - set_campaign_status      (enable / pause a campaign)
#   - update_campaign_budget   (change daily budget in BRL)
#   - set_campaign_target_roas (set Target ROAS on Maximize Conversion Value campaigns)
#   - rename_campaign          (rename a campaign)

"""Tools for mutating Google Ads resources via the MCP server."""

from typing import Literal
from ads_mcp.coordinator import mcp
import ads_mcp.utils as utils
from google.protobuf import field_mask_pb2


@mcp.tool()
def set_campaign_status(
    customer_id: str,
    campaign_id: str,
    status: Literal["ENABLED", "PAUSED"],
) -> str:
    """Enable or pause a Google Ads campaign.

    Args:
        customer_id: The customer/account ID without hyphens (e.g. '5521940727')
        campaign_id: The campaign ID to update (e.g. '21187695750')
        status: New status — ENABLED to activate, PAUSED to pause
    """
    client = utils.get_googleads_client()
    campaign_service = utils.get_googleads_service("CampaignService")

    campaign_operation = client.get_type("CampaignOperation")
    campaign = campaign_operation.update
    campaign.resource_name = f"customers/{customer_id}/campaigns/{campaign_id}"

    if status == "ENABLED":
        campaign.status = client.enums.CampaignStatusEnum.ENABLED
    elif status == "PAUSED":
        campaign.status = client.enums.CampaignStatusEnum.PAUSED
    else:
        return f"Error: invalid status '{status}'. Use ENABLED or PAUSED."

    campaign_operation.update_mask.CopyFrom(
        field_mask_pb2.FieldMask(paths=["status"])
    )

    response = campaign_service.mutate_campaigns(
        customer_id=str(customer_id),
        operations=[campaign_operation],
    )

    resource = response.results[0].resource_name
    return f"OK: Campaign {campaign_id} is now {status}. Resource: {resource}"


@mcp.tool()
def update_campaign_budget(
    customer_id: str,
    campaign_id: str,
    daily_budget_brl: float,
) -> str:
    """Update the daily budget of a Google Ads campaign.

    Args:
        customer_id: The customer/account ID without hyphens
        campaign_id: The campaign ID whose budget will be updated
        daily_budget_brl: New daily budget in Brazilian Reais (e.g., 100.0 for R$100/day)
    """
    # Resolve the campaign budget resource name first
    ga_service = utils.get_googleads_service("GoogleAdsService")
    query = (
        f"SELECT campaign_budget.resource_name "
        f"FROM campaign "
        f"WHERE campaign.id = {campaign_id}"
    )
    stream = ga_service.search_stream(customer_id=str(customer_id), query=query)

    budget_resource_name = None
    for batch in stream:
        for row in batch.results:
            budget_resource_name = row.campaign_budget.resource_name
            break
        if budget_resource_name:
            break

    if not budget_resource_name:
        return f"Error: budget resource not found for campaign {campaign_id}."

    amount_micros = int(daily_budget_brl * 1_000_000)

    client = utils.get_googleads_client()
    budget_service = utils.get_googleads_service("CampaignBudgetService")

    budget_operation = client.get_type("CampaignBudgetOperation")
    budget = budget_operation.update
    budget.resource_name = budget_resource_name
    budget.amount_micros = amount_micros

    budget_operation.update_mask.CopyFrom(
        field_mask_pb2.FieldMask(paths=["amount_micros"])
    )

    response = budget_service.mutate_campaign_budgets(
        customer_id=str(customer_id),
        operations=[budget_operation],
    )

    resource = response.results[0].resource_name
    return (
        f"OK: Campaign {campaign_id} budget updated to "
        f"R${daily_budget_brl:.2f}/day ({amount_micros:,} micros). "
        f"Resource: {resource}"
    )


@mcp.tool()
def set_campaign_target_roas(
    customer_id: str,
    campaign_id: str,
    target_roas: float,
) -> str:
    """Set the Target ROAS for a Maximize Conversion Value campaign.

    Args:
        customer_id: The customer/account ID without hyphens
        campaign_id: The campaign ID to update
        target_roas: Target ROAS multiplier (e.g., 6.0 = 600% = 6x ROAS).
                     Set to 0.0 to remove the target and run unconstrained.
    """
    client = utils.get_googleads_client()
    campaign_service = utils.get_googleads_service("CampaignService")

    campaign_operation = client.get_type("CampaignOperation")
    campaign = campaign_operation.update
    campaign.resource_name = f"customers/{customer_id}/campaigns/{campaign_id}"
    campaign.maximize_conversion_value.target_roas = target_roas

    campaign_operation.update_mask.CopyFrom(
        field_mask_pb2.FieldMask(paths=["maximize_conversion_value.target_roas"])
    )

    response = campaign_service.mutate_campaigns(
        customer_id=str(customer_id),
        operations=[campaign_operation],
    )

    resource = response.results[0].resource_name
    if target_roas > 0:
        roas_str = f"{target_roas:.1f}x ({target_roas * 100:.0f}%)"
    else:
        roas_str = "removed (unconstrained Maximize Conversion Value)"
    return f"OK: Campaign {campaign_id} Target ROAS set to {roas_str}. Resource: {resource}"


@mcp.tool()
def rename_campaign(
    customer_id: str,
    campaign_id: str,
    new_name: str,
) -> str:
    """Rename a Google Ads campaign.

    Args:
        customer_id: The customer/account ID without hyphens (e.g. '5521940727')
        campaign_id: The campaign ID to rename (e.g. '21187695750')
        new_name: The new display name for the campaign
    """
    client = utils.get_googleads_client()
    campaign_service = utils.get_googleads_service("CampaignService")

    campaign_operation = client.get_type("CampaignOperation")
    campaign = campaign_operation.update
    campaign.resource_name = f"customers/{customer_id}/campaigns/{campaign_id}"
    campaign.name = new_name

    campaign_operation.update_mask.CopyFrom(
        field_mask_pb2.FieldMask(paths=["name"])
    )

    response = campaign_service.mutate_campaigns(
        customer_id=str(customer_id),
        operations=[campaign_operation],
    )

    resource = response.results[0].resource_name
    return f"OK: Campaign {campaign_id} renamed to '{new_name}'. Resource: {resource}"
