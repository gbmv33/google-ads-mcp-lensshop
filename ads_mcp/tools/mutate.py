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


# ── Asset Group tools (LensShop addition) ─────────────────────────────────────

@mcp.tool()
def update_asset_group_urls(
    customer_id: str,
    asset_group_id: str,
    final_url: str,
    path1: str = "",
    path2: str = "",
) -> str:
    """Update the final URL and display paths of a PMax asset group.

    Args:
        customer_id: Account ID without hyphens (e.g. '5521940727')
        asset_group_id: Asset group ID (e.g. '6713279038')
        final_url: Landing page URL (e.g. 'https://www.lensshop.com.br/collections/lentes-de-contato')
        path1: First display path shown after domain (e.g. 'lentes-de-contato')
        path2: Second display path — leave empty if not needed
    """
    client = utils.get_googleads_client()
    ag_service = utils.get_googleads_service("AssetGroupService")

    ag_op = client.get_type("AssetGroupOperation")
    ag = ag_op.update
    ag.resource_name = f"customers/{customer_id}/assetGroups/{asset_group_id}"
    ag.final_urls[:] = [final_url]
    ag.path1 = path1
    ag.path2 = path2

    ag_op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["final_urls", "path1", "path2"]))

    response = ag_service.mutate_asset_groups(customer_id=str(customer_id), operations=[ag_op])
    resource = response.results[0].resource_name
    display = f"{final_url.replace('https://', '').replace('http://', '').split('/')[0]}/{path1}/{path2}".rstrip("/")
    return f"OK: Asset group {asset_group_id} URL → {final_url} | display: {display}. Resource: {resource}"


@mcp.tool()
def add_text_asset_to_group(
    customer_id: str,
    asset_group_id: str,
    text: str,
    field_type: str,
) -> str:
    """Add a new headline, long headline or description to a PMax asset group.

    Args:
        customer_id: Account ID without hyphens
        asset_group_id: Asset group ID (e.g. '6713279038')
        text: Text content of the asset
        field_type: HEADLINE (max 30 chars), LONG_HEADLINE (max 90 chars), DESCRIPTION (max 90 chars)
    """
    limits = {"HEADLINE": 30, "LONG_HEADLINE": 90, "DESCRIPTION": 90}
    if field_type not in limits:
        return f"Error: field_type must be one of {list(limits.keys())}"
    if len(text) > limits[field_type]:
        return f"Error: '{text}' has {len(text)} chars — {field_type} max is {limits[field_type]}."

    client = utils.get_googleads_client()

    # Step 1 — create text asset
    asset_service = utils.get_googleads_service("AssetService")
    asset_op = client.get_type("AssetOperation")
    asset = asset_op.create
    asset.text_asset.text = text
    asset.name = text[:50]

    asset_resp = asset_service.mutate_assets(customer_id=str(customer_id), operations=[asset_op])
    asset_resource = asset_resp.results[0].resource_name

    # Step 2 — link asset to asset group
    aga_service = utils.get_googleads_service("AssetGroupAssetService")
    aga_op = client.get_type("AssetGroupAssetOperation")
    aga = aga_op.create
    aga.asset_group = f"customers/{customer_id}/assetGroups/{asset_group_id}"
    aga.asset = asset_resource
    aga.field_type = getattr(client.enums.AssetFieldTypeEnum, field_type)

    aga_resp = aga_service.mutate_asset_group_assets(customer_id=str(customer_id), operations=[aga_op])
    aga_resource = aga_resp.results[0].resource_name
    return f"OK: {field_type} "{text}" added to asset group {asset_group_id}. Resource: {aga_resource}"


@mcp.tool()
def remove_asset_from_group(
    customer_id: str,
    asset_group_id: str,
    asset_resource_name: str,
    field_type: str,
) -> str:
    """Remove an asset (headline, description, image) from a PMax asset group.

    Args:
        customer_id: Account ID without hyphens
        asset_group_id: Asset group ID (e.g. '6713279038')
        asset_resource_name: Full asset resource name from search results
                             (e.g. 'customers/5521940727/assets/122065521208')
        field_type: HEADLINE, LONG_HEADLINE, DESCRIPTION, AD_IMAGE, MARKETING_IMAGE,
                    SQUARE_MARKETING_IMAGE, PORTRAIT_MARKETING_IMAGE, YOUTUBE_VIDEO
    """
    client = utils.get_googleads_client()
    ga_service = utils.get_googleads_service("GoogleAdsService")

    # Resolve exact resource name via query (avoids manually constructing enum int)
    ag_resource = f"customers/{customer_id}/assetGroups/{asset_group_id}"
    query = (
        f"SELECT asset_group_asset.resource_name "
        f"FROM asset_group_asset "
        f"WHERE asset_group_asset.asset_group = "{ag_resource}" "
        f"AND asset_group_asset.asset = "{asset_resource_name}" "
        f"AND asset_group_asset.field_type = "{field_type}""
    )
    stream = ga_service.search_stream(customer_id=str(customer_id), query=query)
    resource_name = None
    for batch in stream:
        for row in batch.results:
            resource_name = row.asset_group_asset.resource_name
            break
        if resource_name:
            break

    if not resource_name:
        return f"Error: asset '{asset_resource_name}' with field_type {field_type} not found in group {asset_group_id}."

    aga_service = utils.get_googleads_service("AssetGroupAssetService")
    aga_op = client.get_type("AssetGroupAssetOperation")
    aga_op.remove = resource_name

    aga_service.mutate_asset_group_assets(customer_id=str(customer_id), operations=[aga_op])
    asset_id = asset_resource_name.split("/")[-1]
    return f"OK: Asset {asset_id} ({field_type}) removed from asset group {asset_group_id}."
