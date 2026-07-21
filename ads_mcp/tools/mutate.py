# LensShop customization — Google Ads write operations via MCP
#
# Adds mutation tools not present in the upstream package:
#   - set_campaign_status                  (enable / pause a campaign)
#   - update_campaign_budget               (change daily budget in BRL)
#   - set_campaign_target_roas             (set Target ROAS on Maximize Conversion Value campaigns)
#   - rename_campaign                      (rename a campaign)
#   - rename_asset_group                   (rename a PMax asset group)
#   - archive_audiences                    (archive / soft-delete audience resources by ID)
#   - create_conversion_action             (create a new conversion action and return its label)
#   - list_user_lists                      (list remarketing / customer match lists in the account)
#   - add_asset_group_audience_signal      (add a single audience signal to a PMax asset group)
#   - set_asset_group_audience_signals     (set combined multi-list audience signal on a PMax asset group)
#   - set_campaign_ad_schedule             (configure day-parting / ad schedule for a campaign)
#   - set_conversion_action_primary        (promote/demote a conversion action to primary or secondary)
#   - add_text_asset_to_asset_group        (add a headline, description, or long headline to a PMax asset group)
#   - remove_asset_from_asset_group        (remove/unlink an asset from a PMax asset group by ID)
#   - upload_logo_to_asset_group           (upload a logo from URL or file path and add it to a PMax asset group)
#   - upload_logo_to_campaign              (upload a logo and link at campaign level — required when Brand Guidelines is enabled)
#   - add_negative_keywords                (bulk-add negative broad-match keywords to a campaign)
#   - set_campaign_geo_target_type         (change positive geo target type, e.g. PRESENCE_OR_INTEREST → PRESENCE)
#   - set_recommendation_subscription_status (enable/pause an account-level recommendation auto-apply)
#   - set_ad_group_ad_status              (enable/pause/remove a single ad — required to retire an RSA)
#   - create_customer_match_list            (create an empty CRM-based Customer Match user list)
#   - upload_customer_match_members         (hash + upload emails/phones into a Customer Match list, async job)
#   - remove_user_list                      (permanently delete an orphaned/unused user list)

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
def rename_asset_group(
    customer_id: str,
    asset_group_id: str,
    new_name: str,
) -> str:
    """Rename a PMax asset group.

    Args:
        customer_id: The customer/account ID without hyphens (e.g. '5521940727')
        asset_group_id: The asset group ID to rename (e.g. '6713279038')
        new_name: The new display name for the asset group
    """
    client = utils.get_googleads_client()
    ag_service = utils.get_googleads_service("AssetGroupService")

    operation = client.get_type("AssetGroupOperation")
    ag = operation.update
    ag.resource_name = f"customers/{customer_id}/assetGroups/{asset_group_id}"
    ag.name = new_name

    operation.update_mask.CopyFrom(
        field_mask_pb2.FieldMask(paths=["name"])
    )

    response = ag_service.mutate_asset_groups(
        customer_id=str(customer_id),
        operations=[operation],
    )

    resource = response.results[0].resource_name
    return f"OK: Asset group {asset_group_id} renamed to '{new_name}'. Resource: {resource}"


@mcp.tool()
def archive_audiences(
    customer_id: str,
    audience_ids: list[str],
) -> str:
    """Archive (soft-delete) audience resources by ID.

    Sets the status of each audience to REMOVED, cleaning up unused audiences
    without permanently deleting their history.

    Args:
        customer_id: The customer/account ID without hyphens (e.g. '5521940727')
        audience_ids: List of audience IDs to archive (e.g. ['349822096', '349822099'])
    """
    client = utils.get_googleads_client()
    audience_service = utils.get_googleads_service("AudienceService")

    operations = []
    for aud_id in audience_ids:
        op = client.get_type("AudienceOperation")
        aud = op.update
        aud.resource_name = f"customers/{customer_id}/audiences/{aud_id}"
        aud.status = client.enums.AudienceStatusEnum.REMOVED
        op.update_mask.CopyFrom(
            field_mask_pb2.FieldMask(paths=["status"])
        )
        operations.append(op)

    response = audience_service.mutate_audiences(
        customer_id=str(customer_id),
        operations=operations,
    )

    archived = [r.resource_name for r in response.results]
    return (
        f"OK: {len(archived)} audience(s) arquivada(s).\n"
        + "\n".join(f"  {r}" for r in archived)
    )


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
def list_user_lists(customer_id: str) -> str:
    """List all user lists (remarketing and customer match) available in the account.

    Returns each list's ID, name, type, and resource name. The resource name
    can be passed directly to add_asset_group_audience_signal to configure
    PMax audience signals.

    Args:
        customer_id: The customer/account ID without hyphens (e.g. '5521940727')
    """
    ga_service = utils.get_googleads_service("GoogleAdsService")
    query = (
        "SELECT user_list.id, user_list.name, user_list.type, "
        "user_list.membership_status, user_list.size_for_search "
        "FROM user_list "
        "WHERE user_list.membership_status = 'OPEN' "
        "ORDER BY user_list.size_for_search DESC"
    )
    stream = ga_service.search_stream(customer_id=str(customer_id), query=query)

    lines = []
    for batch in stream:
        for row in batch.results:
            ul = row.user_list
            resource = f"customers/{customer_id}/userLists/{ul.id}"
            lines.append(
                f"ID: {ul.id} | {ul.name} | Tipo: {ul.type_.name} | "
                f"Tamanho Search: {ul.size_for_search:,} usuários | "
                f"resource_name: {resource}"
            )

    if not lines:
        return "Nenhuma user list ativa encontrada nessa conta."
    return "\n".join(lines)


@mcp.tool()
def add_asset_group_audience_signal(
    customer_id: str,
    asset_group_id: str,
    audience_resource_name: str,
) -> str:
    """Add an audience signal to a Performance Max asset group.

    Audience signals tell the PMax algorithm which audiences are most likely
    to convert, dramatically speeding up optimisation. Use list_user_lists()
    to discover available remarketing / customer-match list resource names.

    If a userList resource name is given, an Audience wrapper is automatically
    created before adding the signal (required by the Google Ads API).

    Args:
        customer_id: The customer/account ID without hyphens (e.g. '5521940727')
        asset_group_id: The PMax asset group ID (e.g. '6713279038')
        audience_resource_name: Full resource name of the audience or user list.
            User list  → customers/{customer_id}/userLists/{user_list_id}
            Audience   → customers/{customer_id}/audiences/{audience_id}
    """
    client = utils.get_googleads_client()
    actual_audience_resource = audience_resource_name
    created_audience_resource = None

    # The AssetGroupSignal.audience.audience field only accepts Audience resources.
    # When given a userList, we create a thin Audience wrapper first.
    if "/userLists/" in audience_resource_name:
        list_id = audience_resource_name.split("/")[-1]

        audience_service = utils.get_googleads_service("AudienceService")
        op = client.get_type("AudienceOperation")
        aud = op.create
        aud.name = f"[MCP Signal] UserList {list_id}"

        seg = client.get_type("AudienceSegment")
        seg.user_list.user_list = audience_resource_name

        dim = client.get_type("AudienceDimension")
        dim.audience_segments.segments.append(seg)

        aud.dimensions.append(dim)

        aud_response = audience_service.mutate_audiences(
            customer_id=str(customer_id),
            operations=[op],
        )
        actual_audience_resource = aud_response.results[0].resource_name
        created_audience_resource = actual_audience_resource

    signal_service = utils.get_googleads_service("AssetGroupSignalService")
    operation = client.get_type("AssetGroupSignalOperation")
    signal = operation.create
    signal.asset_group = f"customers/{customer_id}/assetGroups/{asset_group_id}"
    signal.audience.audience = actual_audience_resource

    response = signal_service.mutate_asset_group_signals(
        customer_id=str(customer_id),
        operations=[operation],
    )

    resource = response.results[0].resource_name
    msg = f"OK: Sinal de audiência adicionado ao asset group {asset_group_id}.\n"
    if created_audience_resource:
        msg += f"  UserList: {audience_resource_name}\n"
        msg += f"  Audience criada: {created_audience_resource}\n"
    else:
        msg += f"  Audiência: {actual_audience_resource}\n"
    msg += f"  Signal resource: {resource}"
    return msg


@mcp.tool()
def set_asset_group_audience_signals(
    customer_id: str,
    asset_group_id: str,
    user_list_ids: list[str],
    audience_name: str = "",
) -> str:
    """Set a combined audience signal on a PMax asset group using multiple user lists.

    The Google Ads API allows only ONE audience signal per asset group.
    This tool creates a single Audience that wraps all specified user lists as
    segments (OR logic), then sets it as the asset group signal. If a signal
    already exists it is removed first.

    Use list_user_lists() to discover available user list IDs.

    Args:
        customer_id: The customer/account ID without hyphens (e.g. '5521940727')
        asset_group_id: The PMax asset group ID (e.g. '6713279038')
        user_list_ids: List of user list IDs to combine (e.g. ['8458077051', '9033427680'])
        audience_name: Optional display name for the combined Audience resource.
                       Defaults to '[MCP Signal] Combined <asset_group_id>'.
    """
    client = utils.get_googleads_client()
    ga_service = utils.get_googleads_service("GoogleAdsService")

    # 1. Remove any existing audience signal on this asset group
    existing_query = (
        f"SELECT asset_group_signal.resource_name "
        f"FROM asset_group_signal "
        f"WHERE asset_group.id = {asset_group_id}"
    )
    stream = ga_service.search_stream(customer_id=str(customer_id), query=existing_query)
    removed = []
    signal_service = utils.get_googleads_service("AssetGroupSignalService")
    for batch in stream:
        for row in batch.results:
            rn = row.asset_group_signal.resource_name
            remove_op = client.get_type("AssetGroupSignalOperation")
            remove_op.remove = rn
            signal_service.mutate_asset_group_signals(
                customer_id=str(customer_id),
                operations=[remove_op],
            )
            removed.append(rn)

    # 2. Build a combined Audience with one dimension per user list (OR semantics)
    name = audience_name or f"[MCP Signal] Combined {asset_group_id}"
    audience_service = utils.get_googleads_service("AudienceService")
    op = client.get_type("AudienceOperation")
    aud = op.create
    aud.name = name

    # All user lists must live inside a SINGLE AudienceSegmentDimension (OR semantics).
    # The API rejects multiple dimensions of the same type.
    dim = client.get_type("AudienceDimension")
    for ul_id in user_list_ids:
        ul_resource = f"customers/{customer_id}/userLists/{ul_id}"
        seg = client.get_type("AudienceSegment")
        seg.user_list.user_list = ul_resource
        dim.audience_segments.segments.append(seg)
    aud.dimensions.append(dim)

    aud_response = audience_service.mutate_audiences(
        customer_id=str(customer_id),
        operations=[op],
    )
    audience_resource = aud_response.results[0].resource_name

    # 3. Add the combined audience as the new signal
    signal_op = client.get_type("AssetGroupSignalOperation")
    signal = signal_op.create
    signal.asset_group = f"customers/{customer_id}/assetGroups/{asset_group_id}"
    signal.audience.audience = audience_resource

    sig_response = signal_service.mutate_asset_group_signals(
        customer_id=str(customer_id),
        operations=[signal_op],
    )
    signal_resource = sig_response.results[0].resource_name

    lines = [
        f"OK: Sinais de audiência configurados no asset group {asset_group_id}.",
        f"  Sinais anteriores removidos: {len(removed)}",
        f"  Audience combinada criada: {audience_resource}",
        f"  User lists incluídas ({len(user_list_ids)}): {', '.join(user_list_ids)}",
        f"  Signal resource: {signal_resource}",
    ]
    return "\n".join(lines)


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
    is allowed to serve — it does not support bid adjustments per hour.

    Args:
        customer_id: The customer/account ID without hyphens (e.g. '5521940727')
        campaign_id: The campaign ID to configure (e.g. '23846742651')
        start_hour: Hour to START serving, 0–23 (e.g. 8 for 08:00)
        end_hour: Hour to STOP serving, 1–24 (e.g. 23 for 23:00)
        days: Days to apply the schedule. Defaults to all 7 days.
              Valid values: MONDAY TUESDAY WEDNESDAY THURSDAY FRIDAY SATURDAY SUNDAY
    """
    if days is None:
        days = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]

    client = utils.get_googleads_client()
    ga_service = utils.get_googleads_service("GoogleAdsService")
    criterion_service = utils.get_googleads_service("CampaignCriterionService")

    # 1. Remove existing ad schedule criteria for this campaign
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

    # 2. Create new criteria for each requested day
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
                f"Error: dia inválido '{day_name}'. "
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
        f"OK: Programação de anúncios configurada para a campanha {campaign_id}.\n"
        f"  Critérios anteriores removidos: {removed_count}\n"
        f"  Novos critérios criados: {created_count}\n"
        f"  Horário: {start_hour:02d}:00 – {end_hour:02d}:00\n"
        f"  Dias: {days_str}\n"
        f"  A campanha não exibirá anúncios fora desse intervalo."
    )


@mcp.tool()
def set_conversion_action_primary(
    customer_id: str,
    conversion_action_id: str,
    include_in_conversions: bool,
) -> str:
    """Promote or demote a conversion action between primary and secondary.

    Primary (True)  → included in 'Conversions' column; used by Smart Bidding for optimisation.
    Secondary (False) → appears only in 'All Conversions'; ignored by Smart Bidding.

    Use this to ensure Smart Bidding optimises exclusively for purchases by demoting
    non-revenue signals (e.g. phone calls) to secondary.

    Args:
        customer_id: The customer/account ID without hyphens (e.g. '5521940727')
        conversion_action_id: Numeric ID of the conversion action to update
        include_in_conversions: True = primary, False = secondary
    """
    client = utils.get_googleads_client()
    conversion_service = client.get_service("ConversionActionService")

    operation = client.get_type("ConversionActionOperation")
    ca = operation.update
    ca.resource_name = f"customers/{customer_id}/conversionActions/{conversion_action_id}"
    ca.include_in_conversions_metric = include_in_conversions

    operation.update_mask.CopyFrom(
        field_mask_pb2.FieldMask(paths=["include_in_conversions_metric"])
    )

    response = conversion_service.mutate_conversion_actions(
        customer_id=str(customer_id),
        operations=[operation],
    )

    resource = response.results[0].resource_name
    status = "primária (incluída em Conversões)" if include_in_conversions else "secundária (excluída de Conversões — apenas All Conversions)"
    return f"OK: Conversion action {conversion_action_id} agora é {status}.\n  Resource: {resource}"


@mcp.tool()
def add_text_asset_to_asset_group(
    customer_id: str,
    asset_group_id: str,
    field_type: Literal["HEADLINE", "DESCRIPTION", "LONG_HEADLINE"],
    text: str,
) -> str:
    """Add a text asset (headline, description, or long headline) to a PMax asset group.

    Creates a new text asset and links it to the specified asset group.

    Character limits enforced:
    - HEADLINE: max 30 chars
    - DESCRIPTION: max 90 chars
    - LONG_HEADLINE: max 90 chars

    Args:
        customer_id: The customer/account ID without hyphens (e.g. '5521940727')
        asset_group_id: The PMax asset group ID (e.g. '6713279038')
        field_type: Asset type — HEADLINE, DESCRIPTION, or LONG_HEADLINE
        text: The text content for the asset
    """
    limits = {"HEADLINE": 30, "DESCRIPTION": 90, "LONG_HEADLINE": 90}
    limit = limits[field_type]
    if len(text) > limit:
        return f"Error: '{text}' tem {len(text)} caracteres; o máximo para {field_type} é {limit}."

    client = utils.get_googleads_client()
    asset_service = utils.get_googleads_service("AssetService")

    asset_op = client.get_type("AssetOperation")
    asset = asset_op.create
    asset.text_asset.text = text

    asset_response = asset_service.mutate_assets(
        customer_id=str(customer_id),
        operations=[asset_op],
    )
    asset_resource = asset_response.results[0].resource_name
    asset_id = asset_resource.split("/")[-1]

    aga_service = utils.get_googleads_service("AssetGroupAssetService")
    aga_op = client.get_type("AssetGroupAssetOperation")
    aga = aga_op.create
    aga.asset_group = f"customers/{customer_id}/assetGroups/{asset_group_id}"
    aga.asset = asset_resource

    field_type_map = {
        "HEADLINE": client.enums.AssetFieldTypeEnum.HEADLINE,
        "DESCRIPTION": client.enums.AssetFieldTypeEnum.DESCRIPTION,
        "LONG_HEADLINE": client.enums.AssetFieldTypeEnum.LONG_HEADLINE,
    }
    aga.field_type = field_type_map[field_type]

    aga_response = aga_service.mutate_asset_group_assets(
        customer_id=str(customer_id),
        operations=[aga_op],
    )
    aga_resource = aga_response.results[0].resource_name

    return (
        f"OK: {field_type} '{text}' adicionado ao asset group {asset_group_id}.\n"
        f"  Asset ID: {asset_id}\n"
        f"  Asset resource: {asset_resource}\n"
        f"  AssetGroupAsset resource: {aga_resource}"
    )


@mcp.tool()
def remove_asset_from_asset_group(
    customer_id: str,
    asset_group_id: str,
    asset_id: str,
    field_type: Literal[
        "HEADLINE", "DESCRIPTION", "LONG_HEADLINE",
        "MARKETING_IMAGE", "SQUARE_MARKETING_IMAGE", "PORTRAIT_MARKETING_IMAGE",
        "TALL_PORTRAIT_MARKETING_IMAGE", "LOGO", "LANDSCAPE_LOGO",
        "AD_IMAGE", "YOUTUBE_VIDEO",
    ],
) -> str:
    """Remove (unlink) an asset from a PMax asset group.

    Sets the AssetGroupAsset status to REMOVED, unlinking the asset from the group
    without deleting the underlying asset resource.

    Use the search tool with resource=asset_group_asset to find asset IDs and field
    types before calling this.

    Args:
        customer_id: The customer/account ID without hyphens (e.g. '5521940727')
        asset_group_id: The PMax asset group ID (e.g. '6713279038')
        asset_id: The numeric asset ID (e.g. '361410988257')
        field_type: The field type the asset is linked with in the asset group
    """
    resource_name = (
        f"customers/{customer_id}/assetGroupAssets/"
        f"{asset_group_id}~{asset_id}~{field_type}"
    )

    client = utils.get_googleads_client()
    aga_service = utils.get_googleads_service("AssetGroupAssetService")

    op = client.get_type("AssetGroupAssetOperation")
    op.remove = resource_name

    response = aga_service.mutate_asset_group_assets(
        customer_id=str(customer_id),
        operations=[op],
    )

    removed_resource = response.results[0].resource_name
    return (
        f"OK: Asset {asset_id} ({field_type}) removido do asset group {asset_group_id}.\n"
        f"  Resource removida: {removed_resource}"
    )


@mcp.tool()
def upload_logo_to_asset_group(
    customer_id: str,
    asset_group_id: str,
    image_source: str,
    logo_type: Literal["LOGO", "LANDSCAPE_LOGO"] = "LOGO",
    asset_name: str = "",
) -> str:
    """Upload a logo image and add it to a PMax asset group.

    Accepts a local file path or a public HTTPS URL to the image file.
    The image is uploaded as an ImageAsset and linked to the asset group.

    Recommended specs:
    - LOGO (square 1:1): 1200×1200 px, PNG with transparent background, max 5 MB
    - LANDSCAPE_LOGO (4:1): 1200×300 px, PNG/JPG, max 5 MB

    Args:
        customer_id: The customer/account ID without hyphens (e.g. '5521940727')
        asset_group_id: The PMax asset group ID (e.g. '6713279038')
        image_source: Local file path (e.g. 'C:/images/logo.png') or public URL
        logo_type: LOGO for square (1:1), LANDSCAPE_LOGO for horizontal (4:1)
        asset_name: Optional display name for the asset. Defaults to the filename.
    """
    import urllib.request
    import os

    if image_source.startswith("http://") or image_source.startswith("https://"):
        req = urllib.request.Request(
            image_source,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            image_data = resp.read()
        filename = image_source.split("/")[-1].split("?")[0] or logo_type
    else:
        with open(image_source, "rb") as f:
            image_data = f.read()
        filename = os.path.basename(image_source)

    name = asset_name or filename

    client = utils.get_googleads_client()
    asset_service = utils.get_googleads_service("AssetService")

    asset_op = client.get_type("AssetOperation")
    asset = asset_op.create
    asset.name = name
    asset.image_asset.data = image_data

    asset_response = asset_service.mutate_assets(
        customer_id=str(customer_id),
        operations=[asset_op],
    )
    asset_resource = asset_response.results[0].resource_name
    asset_id = asset_resource.split("/")[-1]

    aga_service = utils.get_googleads_service("AssetGroupAssetService")
    aga_op = client.get_type("AssetGroupAssetOperation")
    aga = aga_op.create
    aga.asset_group = f"customers/{customer_id}/assetGroups/{asset_group_id}"
    aga.asset = asset_resource

    field_type_map = {
        "LOGO": client.enums.AssetFieldTypeEnum.LOGO,
        "LANDSCAPE_LOGO": client.enums.AssetFieldTypeEnum.LANDSCAPE_LOGO,
    }
    aga.field_type = field_type_map[logo_type]

    aga_response = aga_service.mutate_asset_group_assets(
        customer_id=str(customer_id),
        operations=[aga_op],
    )
    aga_resource = aga_response.results[0].resource_name

    size_kb = len(image_data) / 1024
    return (
        f"OK: Logo '{name}' ({size_kb:.1f} KB) enviado como {logo_type} "
        f"e adicionado ao asset group {asset_group_id}.\n"
        f"  Asset ID: {asset_id}\n"
        f"  Asset resource: {asset_resource}\n"
        f"  AssetGroupAsset resource: {aga_resource}"
    )


@mcp.tool()
def upload_logo_to_campaign(
    customer_id: str,
    campaign_id: str,
    image_source: str,
    logo_type: Literal["LOGO", "LANDSCAPE_LOGO"] = "LOGO",
    asset_name: str = "",
) -> str:
    """Upload a logo image and link it at the CAMPAIGN level (required when Brand Guidelines is enabled).

    Use this instead of upload_logo_to_asset_group when the PMax campaign has Brand Guidelines
    (Diretrizes de Marca) enabled. In that mode, logo and business name must be CampaignAssets,
    not AssetGroupAssets.

    Recommended specs:
    - LOGO (square 1:1): 1200×1200 px, PNG with transparent background, max 5 MB
    - LANDSCAPE_LOGO (4:1): 1200×300 px, PNG/JPG, max 5 MB

    Args:
        customer_id: The customer/account ID without hyphens (e.g. '5521940727')
        campaign_id: The campaign ID to attach the logo to (e.g. '23846742651')
        image_source: Local file path (e.g. 'D:/images/logo.png') or public HTTPS URL
        logo_type: LOGO for square (1:1), LANDSCAPE_LOGO for horizontal (4:1)
        asset_name: Optional display name for the asset. Defaults to the filename.
    """
    import urllib.request
    import os

    if image_source.startswith("http://") or image_source.startswith("https://"):
        req = urllib.request.Request(
            image_source,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            image_data = resp.read()
        filename = image_source.split("/")[-1].split("?")[0] or logo_type
    else:
        with open(image_source, "rb") as f:
            image_data = f.read()
        filename = os.path.basename(image_source)

    name = asset_name or filename

    client = utils.get_googleads_client()
    asset_service = utils.get_googleads_service("AssetService")

    # 1. Upload the image as an ImageAsset
    asset_op = client.get_type("AssetOperation")
    asset = asset_op.create
    asset.name = name
    asset.image_asset.data = image_data

    asset_response = asset_service.mutate_assets(
        customer_id=str(customer_id),
        operations=[asset_op],
    )
    asset_resource = asset_response.results[0].resource_name
    asset_id = asset_resource.split("/")[-1]

    # 2. Link to campaign as CampaignAsset (required for Brand Guidelines)
    ca_service = utils.get_googleads_service("CampaignAssetService")
    ca_op = client.get_type("CampaignAssetOperation")
    ca = ca_op.create
    ca.campaign = f"customers/{customer_id}/campaigns/{campaign_id}"
    ca.asset = asset_resource

    field_type_map = {
        "LOGO": client.enums.AssetFieldTypeEnum.LOGO,
        "LANDSCAPE_LOGO": client.enums.AssetFieldTypeEnum.LANDSCAPE_LOGO,
    }
    ca.field_type = field_type_map[logo_type]

    ca_response = ca_service.mutate_campaign_assets(
        customer_id=str(customer_id),
        operations=[ca_op],
    )
    ca_resource = ca_response.results[0].resource_name

    size_kb = len(image_data) / 1024
    return (
        f"OK: Logo '{name}' ({size_kb:.1f} KB) enviado como {logo_type} "
        f"e vinculado à campanha {campaign_id} (nível CampaignAsset — Brand Guidelines).\n"
        f"  Asset ID: {asset_id}\n"
        f"  Asset resource: {asset_resource}\n"
        f"  CampaignAsset resource: {ca_resource}"
    )


@mcp.tool()
def add_negative_keywords(
    customer_id: str,
    campaign_id: str,
    keywords: list[str],
    match_type: Literal["BROAD", "PHRASE", "EXACT"] = "BROAD",
) -> str:
    """Bulk-add negative keywords to a Google Ads campaign.

    Adds each keyword as a negative campaign criterion. Duplicate or already-existing
    keywords are silently skipped by the API.

    Args:
        customer_id: The customer/account ID without hyphens (e.g. '5521940727')
        campaign_id: The campaign ID to add negatives to (e.g. '23846742651')
        keywords: List of keyword texts to add as negatives (e.g. ['lasik', 'tutorial'])
        match_type: Keyword match type — BROAD (default), PHRASE, or EXACT
    """
    client = utils.get_googleads_client()
    criterion_service = utils.get_googleads_service("CampaignCriterionService")

    match_type_map = {
        "BROAD": client.enums.KeywordMatchTypeEnum.BROAD,
        "PHRASE": client.enums.KeywordMatchTypeEnum.PHRASE,
        "EXACT": client.enums.KeywordMatchTypeEnum.EXACT,
    }
    kw_match = match_type_map[match_type]

    operations = []
    for kw_text in keywords:
        op = client.get_type("CampaignCriterionOperation")
        criterion = op.create
        criterion.campaign = f"customers/{customer_id}/campaigns/{campaign_id}"
        criterion.negative = True
        criterion.keyword.text = kw_text
        criterion.keyword.match_type = kw_match
        operations.append(op)

    response = criterion_service.mutate_campaign_criteria(
        customer_id=str(customer_id),
        operations=operations,
    )

    added = [r.resource_name for r in response.results]
    return (
        f"OK: {len(added)} palavra(s)-chave negativa(s) adicionada(s) à campanha {campaign_id}.\n"
        + "\n".join(f"  [{match_type}] {kw}" for kw in keywords)
    )


@mcp.tool()
def set_campaign_geo_target_type(
    customer_id: str,
    campaign_id: str,
    positive_geo_target_type: Literal["PRESENCE", "PRESENCE_OR_INTEREST"] = "PRESENCE",
) -> str:
    """Change the positive geo target type of a Google Ads campaign.

    PRESENCE            → show only to users physically located in the targeted area (recommended for e-commerce)
    PRESENCE_OR_INTEREST → show to users in OR interested in the area (default, broader reach)
    LOCATION_OF_PRESENCE → show only when search explicitly mentions the location

    Args:
        customer_id: The customer/account ID without hyphens (e.g. '5521940727')
        campaign_id: The campaign ID to update (e.g. '23846742651')
        positive_geo_target_type: New geo target type (default: PRESENCE)
    """
    client = utils.get_googleads_client()
    campaign_service = utils.get_googleads_service("CampaignService")

    geo_type_map = {
        "PRESENCE": client.enums.PositiveGeoTargetTypeEnum.PRESENCE,
        "PRESENCE_OR_INTEREST": client.enums.PositiveGeoTargetTypeEnum.PRESENCE_OR_INTEREST,
    }

    operation = client.get_type("CampaignOperation")
    campaign = operation.update
    campaign.resource_name = f"customers/{customer_id}/campaigns/{campaign_id}"
    campaign.geo_target_type_setting.positive_geo_target_type = geo_type_map[positive_geo_target_type]

    operation.update_mask.CopyFrom(
        field_mask_pb2.FieldMask(paths=["geo_target_type_setting.positive_geo_target_type"])
    )

    response = campaign_service.mutate_campaigns(
        customer_id=str(customer_id),
        operations=[operation],
    )

    resource = response.results[0].resource_name
    return (
        f"OK: Campanha {campaign_id} geo target type alterado para {positive_geo_target_type}.\n"
        f"  Resource: {resource}"
    )


@mcp.tool()
def set_recommendation_subscription_status(
    customer_id: str,
    recommendation_type: str,
    status: Literal["ENABLED", "PAUSED"],
) -> str:
    """Enable or pause a recommendation subscription (Google's auto-apply).

    Use this to control which recommendations Google may auto-apply on the
    account. Pause types you do NOT want auto-applied (e.g. RESPONSIVE_SEARCH_AD,
    SET_TARGET_ROAS, USE_BROAD_MATCH_KEYWORD). For Lensshop policy all
    subscriptions must remain PAUSED.

    Args:
        customer_id: The customer/account ID without hyphens (e.g. '5521940727')
        recommendation_type: Recommendation type enum value. Common: 
            RESPONSIVE_SEARCH_AD, KEYWORD, OPTIMIZE_AD_ROTATION,
            TARGET_CPA_OPT_IN, MAXIMIZE_CONVERSIONS_OPT_IN,
            MAXIMIZE_CONVERSION_VALUE_OPT_IN, TARGET_ROAS_OPT_IN,
            MAXIMIZE_CLICKS_OPT_IN, DISPLAY_EXPANSION_OPT_IN,
            USE_BROAD_MATCH_KEYWORD, RESPONSIVE_SEARCH_AD_IMPROVE_AD_STRENGTH,
            SET_TARGET_ROAS, RAISE_TARGET_CPA, LOWER_TARGET_ROAS, SET_TARGET_CPA.
            Discover the full live set via: search recommendation_subscription.
        status: New status. ENABLED to allow auto-apply, PAUSED to block it.
    """
    client = utils.get_googleads_client()
    service = utils.get_googleads_service("RecommendationSubscriptionService")

    operation = client.get_type("RecommendationSubscriptionOperation")
    sub = operation.update
    sub.resource_name = (
        f"customers/{customer_id}/recommendationSubscriptions/{recommendation_type}"
    )

    status_enum = client.enums.RecommendationSubscriptionStatusEnum
    if status == "ENABLED":
        sub.status = status_enum.ENABLED
    elif status == "PAUSED":
        sub.status = status_enum.PAUSED
    else:
        return f"Error: invalid status '{status}'. Use ENABLED or PAUSED."

    operation.update_mask.CopyFrom(
        field_mask_pb2.FieldMask(paths=["status"])
    )

    response = service.mutate_recommendation_subscription(
        customer_id=str(customer_id),
        operations=[operation],
    )

    resource = response.results[0].resource_name
    return (
        f"OK: recommendation_subscription [{recommendation_type}] is now {status}. "
        f"Resource: {resource}"
    )


@mcp.tool()
def set_ad_group_ad_status(
    customer_id: str,
    ad_group_id: str,
    ad_id: str,
    status: Literal["ENABLED", "PAUSED", "REMOVED"],
) -> str:
    """Enable, pause, or remove a single ad within an ad group.

    Required to take an RSA out of rotation after creating a replacement,
    since Google Ads does not allow editing final_url on an existing RSA
    (the standard pattern is create-new + pause-old).

    Args:
        customer_id: The customer/account ID without hyphens (e.g. '5521940727')
        ad_group_id: The ad group ID containing the ad (e.g. '196940702306')
        ad_id: The numeric ad ID to update (e.g. '812664910058')
        status: New status. ENABLED to activate, PAUSED to take out of rotation,
                REMOVED to permanently delete (cannot be reactivated).
    """
    client = utils.get_googleads_client()
    service = utils.get_googleads_service("AdGroupAdService")

    operation = client.get_type("AdGroupAdOperation")
    ad_group_ad = operation.update
    ad_group_ad.resource_name = (
        f"customers/{customer_id}/adGroupAds/{ad_group_id}~{ad_id}"
    )

    enum_ = client.enums.AdGroupAdStatusEnum
    if status == "ENABLED":
        ad_group_ad.status = enum_.ENABLED
    elif status == "PAUSED":
        ad_group_ad.status = enum_.PAUSED
    elif status == "REMOVED":
        ad_group_ad.status = enum_.REMOVED
    else:
        return f"Error: invalid status '{status}'. Use ENABLED, PAUSED, or REMOVED."

    operation.update_mask.CopyFrom(
        field_mask_pb2.FieldMask(paths=["status"])
    )

    response = service.mutate_ad_group_ads(
        customer_id=str(customer_id),
        operations=[operation],
    )
    return (
        f"OK: Ad {ad_id} in ad_group {ad_group_id} is now {status}. "
        f"Resource: {response.results[0].resource_name}"
    )



@mcp.tool()
def create_customer_match_list(
    customer_id: str,
    list_name: str,
    description: str = "",
) -> str:
    """Create a new Customer Match user list (CRM-based, contact-info upload key).

    This creates an empty list container in the account. It does NOT upload any
    members — call upload_customer_match_members() afterwards with the returned
    user_list_id to populate it with hashed customer emails/phones. Once populated,
    attach it to a Performance Max asset group as an audience signal via
    add_asset_group_audience_signal() or set_asset_group_audience_signals() so
    the algorithm learns from real customer profiles.

    Args:
        customer_id: The customer/account ID without hyphens (e.g. '5521940727')
        list_name: Display name for the list (e.g. 'Lensshop — Clientes (base completa)')
        description: Optional description shown in the Audience Manager UI
    """
    client = utils.get_googleads_client()
    service = utils.get_googleads_service("UserListService")

    operation = client.get_type("UserListOperation")
    user_list = operation.create
    user_list.name = list_name
    user_list.description = description or f"Customer Match list created via MCP for {list_name}"
    # 540 = API max (field is ignored for CRM-based/Customer Match lists anyway,
    # but the API still validates the range on write)
    user_list.membership_life_span = 540
    user_list.crm_based_user_list.upload_key_type = (
        client.enums.CustomerMatchUploadKeyTypeEnum.CONTACT_INFO
    )
    user_list.crm_based_user_list.data_source_type = (
        client.enums.UserListCrmDataSourceTypeEnum.FIRST_PARTY
    )

    response = service.mutate_user_lists(
        customer_id=str(customer_id),
        operations=[operation],
    )
    resource_name = response.results[0].resource_name
    list_id = resource_name.split("/")[-1]

    return (
        f"OK: Customer Match list '{list_name}' created (initially empty).\n"
        f"  user_list_id: {list_id}\n"
        f"  Resource: {resource_name}\n"
        f"  Próximo passo: upload_customer_match_members(customer_id, user_list_id='{list_id}', emails=[...])"
    )


@mcp.tool()
def upload_customer_match_members(
    customer_id: str,
    user_list_id: str,
    emails: list[str] = None,
    phone_numbers: list[str] = None,
) -> str:
    """Upload hashed customer contact data into an existing Customer Match list.

    Emails and phone numbers are normalized and hashed with SHA-256 before
    leaving this server — Google Ads only ever receives the hash, never the
    raw contact info. This is additive/idempotent: re-running with a refreshed
    customer list merges new members into the existing list without duplicating
    or removing anyone already matched.

    Processing is asynchronous on Google's side (matching can take from minutes
    up to ~a few hours) — this tool submits the job and returns immediately
    without waiting for it to finish.

    Args:
        customer_id: The customer/account ID without hyphens (e.g. '5521940727')
        user_list_id: The numeric ID of the list (from create_customer_match_list
                       or list_user_lists)
        emails: List of raw customer email addresses (any case/whitespace — normalized here)
        phone_numbers: List of phone numbers in E.164 format (e.g. '+5511999998888')
    """
    import hashlib

    emails = emails or []
    phone_numbers = phone_numbers or []
    if not emails and not phone_numbers:
        return "Error: forneça ao menos uma lista não vazia em emails ou phone_numbers."

    def _hash(value: str) -> str:
        return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()

    client = utils.get_googleads_client()
    job_service = utils.get_googleads_service("OfflineUserDataJobService")

    user_list_resource = f"customers/{customer_id}/userLists/{user_list_id}"

    job = client.get_type("OfflineUserDataJob")
    job.type_ = client.enums.OfflineUserDataJobTypeEnum.CUSTOMER_MATCH_USER_LIST
    job.customer_match_user_list_metadata.user_list = user_list_resource

    create_response = job_service.create_offline_user_data_job(
        customer_id=str(customer_id), job=job
    )
    job_resource_name = create_response.resource_name

    # Build one UserData operation per contact. A single contact can carry both
    # an email and a phone if both are known for the same person, but since we
    # receive them as two separate flat lists here, each entry becomes its own
    # UserData (Google de-dupes/merges matches internally by underlying identity).
    operations = []
    for email in emails:
        if not email or "@" not in email:
            continue
        op = client.get_type("OfflineUserDataJobOperation")
        user_identifier = client.get_type("UserIdentifier")
        user_identifier.hashed_email = _hash(email)
        op.create.user_identifiers.append(user_identifier)
        operations.append(op)

    for phone in phone_numbers:
        if not phone:
            continue
        op = client.get_type("OfflineUserDataJobOperation")
        user_identifier = client.get_type("UserIdentifier")
        user_identifier.hashed_phone_number = _hash(phone)
        op.create.user_identifiers.append(user_identifier)
        operations.append(op)

    if not operations:
        return f"Error: nenhum email/telefone válido encontrado nas listas fornecidas. Job {job_resource_name} criado mas sem operações — abortando sem rodar."

    # Batch in chunks of 1000 (comfortably under Google's per-request limits)
    CHUNK = 1000
    total_added = 0
    for i in range(0, len(operations), CHUNK):
        chunk = operations[i : i + CHUNK]
        request = client.get_type("AddOfflineUserDataJobOperationsRequest")
        request.resource_name = job_resource_name
        request.operations.extend(chunk)
        request.enable_partial_failure = True
        job_service.add_offline_user_data_job_operations(request=request)
        total_added += len(chunk)

    # Kick off async processing — do NOT block waiting for the LRO to resolve.
    job_service.run_offline_user_data_job(resource_name=job_resource_name)

    return (
        f"OK: Job de upload enviado para a lista {user_list_id}.\n"
        f"  Job resource: {job_resource_name}\n"
        f"  Identificadores enviados: {total_added} ({len(emails)} email(s), {len(phone_numbers)} telefone(s) nas listas de entrada)\n"
        f"  Status: processando de forma assíncrona no Google Ads (minutos a poucas horas).\n"
        f"  Verifique o tamanho da lista depois via list_user_lists(customer_id) — campo 'Tamanho Search'."
    )


@mcp.tool()
def remove_user_list(
    customer_id: str,
    user_list_id: str,
) -> str:
    """Permanently remove a user list (Customer Match / remarketing list) from the account.

    Use this to clean up orphaned or unused lists — e.g. a Customer Match list
    that was created but never received members due to an upload blocker.
    This does not affect any other user lists or the audiences that reference
    them; if this list is still attached as an audience signal somewhere,
    remove/replace that signal first.

    Args:
        customer_id: The customer/account ID without hyphens (e.g. '5521940727')
        user_list_id: The numeric ID of the user list to remove (from list_user_lists)
    """
    client = utils.get_googleads_client()
    service = utils.get_googleads_service("UserListService")

    operation = client.get_type("UserListOperation")
    operation.remove = f"customers/{customer_id}/userLists/{user_list_id}"

    response = service.mutate_user_lists(
        customer_id=str(customer_id),
        operations=[operation],
    )
    return f"OK: user list {user_list_id} removida. Resource: {response.results[0].resource_name}"
