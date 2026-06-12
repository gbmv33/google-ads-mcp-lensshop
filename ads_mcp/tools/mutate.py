# LensShop customization — Google Ads write operations via MCP
#
# Adds mutation tools not present in the upstream package:
#   - set_campaign_status        (enable / pause a campaign)
#   - update_campaign_budget     (change daily budget in BRL)
#   - set_campaign_target_roas   (set Target ROAS on Maximize Conversion Value campaigns)
#   - rename_campaign            (rename a campaign)
#   - create_conversion_action   (create a new conversion action and return its label)

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


@mcp.tool()
def create_conversion_action(
    customer_id: str,
    name: str,
    category: Literal["PURCHASE", "ADD_TO_CART", "BEGIN_CHECKOUT", "CONTACT", "PAGE_VIEW"] = "PURCHASE",
    counting_type: Literal["ONE_PER_CLICK", "MANY_PER_CLICK"] = "ONE_PER_CLICK",
    default_value: float = 0.0,
    always_use_default_value: bool = False,
    click_through_lookback_days: int = 30,
) -> str:
    """Create a new Google Ads conversion action of type WEBPAGE and return its conversion label.

    Use this to create a purchase (or other) conversion action that can then be
    set as the destination in Shopify's Google & YouTube app → Settings →
    Conversion measurement → custom destination field.

    Args:
        customer_id: The customer/account ID without hyphens (e.g. '5521940727')
        name: Display name for the conversion action (e.g. 'Compra Shopify — Customer Events')
        category: Conversion category. PURCHASE for sales, ADD_TO_CART, BEGIN_CHECKOUT, etc.
        counting_type: ONE_PER_CLICK (recommended for purchases) or MANY_PER_CLICK
        default_value: Default monetary value when no value is passed (0.0 = dynamic value)
        always_use_default_value: If True, ignore dynamic values and always use default_value
        click_through_lookback_days: Attribution window in days (default 30)
    """
    client = utils.get_googleads_client()
    conversion_service = client.get_service("ConversionActionService")

    operation = client.get_type("ConversionActionOperation")
    ca = operation.create

    ca.name = name
    ca.status = client.enums.ConversionActionStatusEnum.ENABLED

    category_map = {
        "PURCHASE": client.enums.ConversionActionCategoryEnum.PURCHASE,
        "ADD_TO_CART": client.enums.ConversionActionCategoryEnum.ADD_TO_CART,
        "BEGIN_CHECKOUT": client.enums.ConversionActionCategoryEnum.BEGIN_CHECKOUT,
        "CONTACT": client.enums.ConversionActionCategoryEnum.CONTACT,
        "PAGE_VIEW": client.enums.ConversionActionCategoryEnum.PAGE_VIEW,
    }
    ca.category = category_map.get(category, client.enums.ConversionActionCategoryEnum.PURCHASE)
    ca.type_ = client.enums.ConversionActionTypeEnum.WEBPAGE

    counting_map = {
        "ONE_PER_CLICK": client.enums.ConversionActionCountingTypeEnum.ONE_PER_CLICK,
        "MANY_PER_CLICK": client.enums.ConversionActionCountingTypeEnum.MANY_PER_CLICK,
    }
    ca.counting_type = counting_map.get(counting_type, client.enums.ConversionActionCountingTypeEnum.ONE_PER_CLICK)

    ca.value_settings.default_value = default_value
    ca.value_settings.always_use_default_value = always_use_default_value
    ca.click_through_lookback_window_days = click_through_lookback_days
    ca.view_through_lookback_window_days = 1

    response = conversion_service.mutate_conversion_actions(
        customer_id=str(customer_id),
        operations=[operation],
    )

    resource_name = response.results[0].resource_name
    conversion_action_id = resource_name.split("/")[-1]

    # Fetch the conversion label (tag snippet) right after creation
    ga_service = client.get_service("GoogleAdsService")
    query = (
        f"SELECT conversion_action.id, conversion_action.name, "
        f"conversion_action.tag_snippets "
        f"FROM conversion_action "
        f"WHERE conversion_action.id = {conversion_action_id}"
    )
    label = None
    stream = ga_service.search_stream(customer_id=str(customer_id), query=query)
    for batch in stream:
        for row in batch.results:
            for snippet in row.conversion_action.tag_snippets:
                # page_format 2 = HTML, type_ 2 = event snippet
                if snippet.page_format == 2 and snippet.type_ == 2:
                    import re
                    match = re.search(r"AW-\d+/[\w-]+", snippet.event_snippet)
                    if match:
                        label = match.group(0)
                        break
            if label:
                break

    result = (
        f"OK: Conversion action '{name}' created.\n"
        f"  ID: {conversion_action_id}\n"
        f"  Resource: {resource_name}\n"
    )
    if label:
        result += f"  Conversion label: {label}\n"
        result += f"\nUse this in Shopify → Google app → Conversion settings → Destino personalizado:\n  {label}"
    else:
        result += f"  (Label not yet available — query conversion_action {conversion_action_id} in a few minutes)"

    return result


@mcp.tool()
def set_campaign_ad_schedule(
    customer_id: str,
    campaign_id: str,
    start_hour: int,
    end_hour: int,
    days: list[str] | None = None,
) -> str:
    """Set ad schedule (day-parting) for a Google Ads campaign.

    Replaces all existing ad schedule criteria with a new time window.
    For Performance Max campaigns, ad scheduling controls when the campaign
    is allowed to serve -- it does not support bid adjustments per hour.

    Args:
        customer_id: The customer/account ID without hyphens (e.g. '5521940727')
        campaign_id: The campaign ID to configure (e.g. '23846742651')
        start_hour: Hour to START serving, 0-23 (e.g. 8 for 08:00)
        end_hour: Hour to STOP serving, 1-24 (e.g. 23 for 23:00)
        days: Days to apply the schedule. Defaults to all 7 days.
              Valid values: MONDAY TUESDAY WEDNESDAY THURSDAY FRIDAY SATURDAY SUNDAY
    """
    if days is None:
        days = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]

    client = utils.get_googleads_client()
    ga_service = utils.get_googleads_service("GoogleAdsService")
    criterion_service = utils.get_googleads_service("CampaignCriterionService")

    query = (
        f"SELECT campaign_criterion.resource_name "
        f"FROM campaign_criterion "
        f"WHERE campaign.id = {campaign_id} "
        f"AND campaign_criterion.type = 'AD_SCHEDULE'"
    )
    stream = ga_service.search_stream(customer_id=str(customer_id), query=query)
    remove_ops = []
    for batch in stream:
        for row in batch.results:
            op = client.get_type("CampaignCriterionOperation")
            op.remove = row.campaign_criterion.resource_name
            remove_ops.append(op)

    removed_count = 0
    if remove_ops:
        criterion_service.mutate_campaign_criteria(
            customer_id=str(customer_id),
            operations=remove_ops,
        )
        removed_count = len(remove_ops)

    day_enum_map = {
        "MONDAY":    client.enums.DayOfWeekEnum.MONDAY,
        "TUESDAY":   client.enums.DayOfWeekEnum.TUESDAY,
        "WEDNESDAY": client.enums.DayOfWeekEnum.WEDNESDAY,
        "THURSDAY":  client.enums.DayOfWeekEnum.THURSDAY,
        "FRIDAY":    client.enums.DayOfWeekEnum.FRIDAY,
        "SATURDAY":  client.enums.DayOfWeekEnum.SATURDAY,
        "SUNDAY":    client.enums.DayOfWeekEnum.SUNDAY,
    }

    create_ops = []
    for day_name in days:
        day_key = day_name.upper()
        if day_key not in day_enum_map:
            return (
                f"Error: dia invalido '{day_name}'. "
                f"Use: MONDAY TUESDAY WEDNESDAY THURSDAY FRIDAY SATURDAY SUNDAY"
            )
        op = client.get_type("CampaignCriterionOperation")
        criterion = op.create
        criterion.campaign = f"customers/{customer_id}/campaigns/{campaign_id}"
        criterion.ad_schedule.day_of_week = day_enum_map[day_key]
        criterion.ad_schedule.start_hour = start_hour
        criterion.ad_schedule.start_minute = client.enums.MinuteOfHourEnum.ZERO
        criterion.ad_schedule.end_hour = end_hour
        criterion.ad_schedule.end_minute = client.enums.MinuteOfHourEnum.ZERO
        create_ops.append(op)

    response = criterion_service.mutate_campaign_criteria(
        customer_id=str(customer_id),
        operations=create_ops,
    )

    created_count = len(response.results)
    days_str = ", ".join(days)
    return (
        f"OK: Programacao de anuncios configurada para a campanha {campaign_id}.\n"
        f"  Criterios anteriores removidos: {removed_count}\n"
        f"  Novos criterios criados: {created_count}\n"
        f"  Horario: {start_hour:02d}:00 - {end_hour:02d}:00\n"
        f"  Dias: {days_str}\n"
        f"  A campanha nao exibira anuncios fora desse intervalo."
    )
