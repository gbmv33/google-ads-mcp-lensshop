# LensShop customization — campaign creation tools for the Google Ads MCP
#
# Adds the build tools missing from upstream and from mutate.py:
#   - create_search_campaign         (Search campaign + budget, TIS or Max Clicks bidding)
#   - create_ad_group                (standard Search ad group)
#   - add_keywords                   (positive keywords on an ad group)
#   - add_campaign_negative_keywords (campaign-level negatives)
#   - create_responsive_search_ad    (RSA with length validation)
#   - set_conversion_action_primary  (toggle primary_for_goal on a conversion action)
#
# Each tool delegates to a plain *_impl function so scripts on the VPS can
# reuse the logic without going through the MCP layer.

"""Tools for building Google Ads search campaigns via the MCP server."""

from typing import Literal
from ads_mcp.coordinator import mcp
import ads_mcp.utils as utils
from google.protobuf import field_mask_pb2

MAX_HEADLINE_LEN = 30
MAX_DESCRIPTION_LEN = 90

_BRAZIL_GEO_ID = 2076
_PORTUGUESE_LANG_ID = 1014


def create_search_campaign_impl(
    customer_id: str,
    name: str,
    daily_budget_brl: float,
    bidding: str = "MAXIMIZE_CLICKS",
    cpc_ceiling_brl: float = 2.5,
    impression_share_percent: int = 90,
    impression_share_location: str = "ABSOLUTE_TOP_OF_PAGE",
    status: str = "PAUSED",
) -> dict:
    client = utils.get_googleads_client()

    # 1. Dedicated (non-shared) daily budget — reuse if a same-named one exists
    budget_name = f"Orçamento — {name}"
    ga_service = utils.get_googleads_service("GoogleAdsService")
    safe_name = budget_name.replace("'", "\\'")
    existing = ga_service.search(
        customer_id=str(customer_id),
        query=(
            "SELECT campaign_budget.resource_name FROM campaign_budget "
            f"WHERE campaign_budget.name = '{safe_name}'"
        ),
    )
    budget_resource = None
    for row in existing:
        budget_resource = row.campaign_budget.resource_name
        break

    if budget_resource is None:
        budget_service = utils.get_googleads_service("CampaignBudgetService")
        budget_op = client.get_type("CampaignBudgetOperation")
        budget = budget_op.create
        budget.name = budget_name
        budget.amount_micros = int(daily_budget_brl * 1_000_000)
        budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
        budget.explicitly_shared = False
        budget_resp = budget_service.mutate_campaign_budgets(
            customer_id=str(customer_id), operations=[budget_op]
        )
        budget_resource = budget_resp.results[0].resource_name

    # 2. Search-only campaign
    campaign_service = utils.get_googleads_service("CampaignService")
    campaign_op = client.get_type("CampaignOperation")
    campaign = campaign_op.create
    campaign.name = name
    campaign.advertising_channel_type = (
        client.enums.AdvertisingChannelTypeEnum.SEARCH
    )
    campaign.status = (
        client.enums.CampaignStatusEnum.ENABLED
        if status == "ENABLED"
        else client.enums.CampaignStatusEnum.PAUSED
    )
    campaign.campaign_budget = budget_resource
    campaign.network_settings.target_google_search = True
    campaign.network_settings.target_search_network = False
    campaign.network_settings.target_content_network = False
    campaign.network_settings.target_partner_search_network = False
    campaign.geo_target_type_setting.positive_geo_target_type = (
        client.enums.PositiveGeoTargetTypeEnum.PRESENCE
    )
    # Required declaration since API v24 (campaign targets Brazil only)
    campaign.contains_eu_political_advertising = (
        client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    )

    if bidding == "TARGET_IMPRESSION_SHARE":
        tis = campaign.target_impression_share
        tis.location = client.enums.TargetImpressionShareLocationEnum[
            impression_share_location
        ]
        tis.location_fraction_micros = impression_share_percent * 10_000
        tis.cpc_bid_ceiling_micros = int(cpc_ceiling_brl * 1_000_000)
    elif bidding == "MAXIMIZE_CLICKS":
        campaign.target_spend.cpc_bid_ceiling_micros = int(
            cpc_ceiling_brl * 1_000_000
        )
    elif bidding == "MAXIMIZE_CONVERSIONS":
        # No target CPA / target ROAS — unconstrained by design (LensShop policy).
        client.copy_from(
            campaign.maximize_conversions, client.get_type("MaximizeConversions")
        )
    else:
        raise ValueError(f"bidding inválido: {bidding}")

    campaign_resp = campaign_service.mutate_campaigns(
        customer_id=str(customer_id), operations=[campaign_op]
    )
    campaign_resource = campaign_resp.results[0].resource_name
    campaign_id = campaign_resource.split("/")[-1]

    # 3. Geo (Brazil, presence) + language (Portuguese)
    criterion_service = utils.get_googleads_service("CampaignCriterionService")
    geo_op = client.get_type("CampaignCriterionOperation")
    geo = geo_op.create
    geo.campaign = campaign_resource
    geo.location.geo_target_constant = f"geoTargetConstants/{_BRAZIL_GEO_ID}"

    lang_op = client.get_type("CampaignCriterionOperation")
    lang = lang_op.create
    lang.campaign = campaign_resource
    lang.language.language_constant = f"languageConstants/{_PORTUGUESE_LANG_ID}"

    criterion_service.mutate_campaign_criteria(
        customer_id=str(customer_id), operations=[geo_op, lang_op]
    )

    return {
        "campaign_id": campaign_id,
        "campaign_resource": campaign_resource,
        "budget_resource": budget_resource,
    }


def create_ad_group_impl(
    customer_id: str,
    campaign_id: str,
    name: str,
    cpc_bid_brl: float | None = None,
) -> dict:
    client = utils.get_googleads_client()
    ad_group_service = utils.get_googleads_service("AdGroupService")
    op = client.get_type("AdGroupOperation")
    ad_group = op.create
    ad_group.name = name
    ad_group.campaign = f"customers/{customer_id}/campaigns/{campaign_id}"
    ad_group.type_ = client.enums.AdGroupTypeEnum.SEARCH_STANDARD
    ad_group.status = client.enums.AdGroupStatusEnum.ENABLED
    if cpc_bid_brl:
        ad_group.cpc_bid_micros = int(cpc_bid_brl * 1_000_000)
    resp = ad_group_service.mutate_ad_groups(
        customer_id=str(customer_id), operations=[op]
    )
    resource = resp.results[0].resource_name
    return {"ad_group_id": resource.split("/")[-1], "resource": resource}


def add_keywords_impl(
    customer_id: str,
    ad_group_id: str,
    keywords: list[str],
    match_type: str = "PHRASE",
) -> list[str]:
    client = utils.get_googleads_client()
    criterion_service = utils.get_googleads_service("AdGroupCriterionService")
    ops = []
    for text in keywords:
        op = client.get_type("AdGroupCriterionOperation")
        criterion = op.create
        criterion.ad_group = f"customers/{customer_id}/adGroups/{ad_group_id}"
        criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
        criterion.keyword.text = text
        criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum[match_type]
        ops.append(op)
    resp = criterion_service.mutate_ad_group_criteria(
        customer_id=str(customer_id), operations=ops
    )
    return [r.resource_name for r in resp.results]


def add_campaign_negative_keywords_impl(
    customer_id: str,
    campaign_id: str,
    keywords: list[str],
    match_type: str = "BROAD",
) -> list[str]:
    client = utils.get_googleads_client()
    criterion_service = utils.get_googleads_service("CampaignCriterionService")
    ops = []
    for text in keywords:
        op = client.get_type("CampaignCriterionOperation")
        criterion = op.create
        criterion.campaign = f"customers/{customer_id}/campaigns/{campaign_id}"
        criterion.negative = True
        criterion.keyword.text = text
        criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum[match_type]
        ops.append(op)
    resp = criterion_service.mutate_campaign_criteria(
        customer_id=str(customer_id), operations=ops
    )
    return [r.resource_name for r in resp.results]


def create_responsive_search_ad_impl(
    customer_id: str,
    ad_group_id: str,
    headlines: list[str],
    descriptions: list[str],
    final_url: str,
    path1: str = "",
    path2: str = "",
) -> dict:
    errors = []
    for h in headlines:
        if len(h) > MAX_HEADLINE_LEN:
            errors.append(f"headline com {len(h)} chars (máx {MAX_HEADLINE_LEN}): '{h}'")
    for d in descriptions:
        if len(d) > MAX_DESCRIPTION_LEN:
            errors.append(f"description com {len(d)} chars (máx {MAX_DESCRIPTION_LEN}): '{d}'")
    if len(headlines) < 3:
        errors.append("RSA exige no mínimo 3 headlines")
    if len(descriptions) < 2:
        errors.append("RSA exige no mínimo 2 descriptions")
    if errors:
        raise ValueError("; ".join(errors))

    client = utils.get_googleads_client()
    ad_service = utils.get_googleads_service("AdGroupAdService")
    op = client.get_type("AdGroupAdOperation")
    ad_group_ad = op.create
    ad_group_ad.ad_group = f"customers/{customer_id}/adGroups/{ad_group_id}"
    ad_group_ad.status = client.enums.AdGroupAdStatusEnum.ENABLED
    ad = ad_group_ad.ad
    ad.final_urls.append(final_url)
    for h in headlines:
        asset = client.get_type("AdTextAsset")
        asset.text = h
        ad.responsive_search_ad.headlines.append(asset)
    for d in descriptions:
        asset = client.get_type("AdTextAsset")
        asset.text = d
        ad.responsive_search_ad.descriptions.append(asset)
    if path1:
        ad.responsive_search_ad.path1 = path1
    if path2:
        ad.responsive_search_ad.path2 = path2
    resp = ad_service.mutate_ad_group_ads(
        customer_id=str(customer_id), operations=[op]
    )
    resource = resp.results[0].resource_name
    return {"ad_resource": resource}


def set_conversion_action_primary_impl(
    customer_id: str,
    conversion_action_id: str,
    primary: bool,
) -> str:
    client = utils.get_googleads_client()
    service = utils.get_googleads_service("ConversionActionService")
    op = client.get_type("ConversionActionOperation")
    ca = op.update
    ca.resource_name = (
        f"customers/{customer_id}/conversionActions/{conversion_action_id}"
    )
    ca.primary_for_goal = primary
    op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["primary_for_goal"]))
    resp = service.mutate_conversion_actions(
        customer_id=str(customer_id), operations=[op]
    )
    return resp.results[0].resource_name


# ---------------------------------------------------------------------------
# MCP tool wrappers
# ---------------------------------------------------------------------------

@mcp.tool()
def create_search_campaign(
    customer_id: str,
    name: str,
    daily_budget_brl: float,
    bidding: Literal["MAXIMIZE_CLICKS", "TARGET_IMPRESSION_SHARE", "MAXIMIZE_CONVERSIONS"] = "MAXIMIZE_CLICKS",
    cpc_ceiling_brl: float = 2.5,
    impression_share_percent: int = 90,
    impression_share_location: Literal["ABSOLUTE_TOP_OF_PAGE", "TOP_OF_PAGE", "ANYWHERE_ON_PAGE"] = "ABSOLUTE_TOP_OF_PAGE",
    status: Literal["ENABLED", "PAUSED"] = "PAUSED",
) -> str:
    """Create a Search-only campaign with its own daily budget, targeting Brazil (presence) in Portuguese.

    Bidding options (Target ROAS intentionally NOT offered — LensShop policy):
      MAXIMIZE_CLICKS — Max Clicks with a CPC ceiling (cpc_ceiling_brl)
      TARGET_IMPRESSION_SHARE — for brand defense (impression_share_percent at impression_share_location, CPC capped at cpc_ceiling_brl)
      MAXIMIZE_CONVERSIONS — unconstrained, no tCPA/tROAS

    Args:
        customer_id: The customer/account ID without hyphens (e.g. '5521940727')
        name: Campaign display name
        daily_budget_brl: Daily budget in BRL (dedicated, not shared)
        bidding: Bidding strategy (see above)
        cpc_ceiling_brl: Max CPC ceiling in BRL for MAXIMIZE_CLICKS / TARGET_IMPRESSION_SHARE
        impression_share_percent: Target impression share percentage (TIS only)
        impression_share_location: Where to target the share (TIS only)
        status: Initial status — defaults to PAUSED for safe review before launch
    """
    result = create_search_campaign_impl(
        customer_id, name, daily_budget_brl, bidding, cpc_ceiling_brl,
        impression_share_percent, impression_share_location, status,
    )
    return (
        f"OK: Campaign '{name}' created ({status}).\n"
        f"  ID: {result['campaign_id']}\n"
        f"  Budget: R${daily_budget_brl:.2f}/day\n"
        f"  Bidding: {bidding}\n"
        f"  Resource: {result['campaign_resource']}"
    )


@mcp.tool()
def create_ad_group(
    customer_id: str,
    campaign_id: str,
    name: str,
    cpc_bid_brl: float | None = None,
) -> str:
    """Create a standard Search ad group in a campaign.

    Args:
        customer_id: The customer/account ID without hyphens
        campaign_id: The parent campaign ID
        name: Ad group display name
        cpc_bid_brl: Optional default CPC bid in BRL (ignored by smart bidding strategies)
    """
    result = create_ad_group_impl(customer_id, campaign_id, name, cpc_bid_brl)
    return f"OK: Ad group '{name}' created. ID: {result['ad_group_id']}"


@mcp.tool()
def add_keywords(
    customer_id: str,
    ad_group_id: str,
    keywords: list[str],
    match_type: Literal["EXACT", "PHRASE", "BROAD"] = "PHRASE",
) -> str:
    """Add positive keywords to an ad group.

    Args:
        customer_id: The customer/account ID without hyphens
        ad_group_id: The ad group to receive the keywords
        keywords: Keyword texts, without match-type punctuation (no brackets/quotes)
        match_type: Match type applied to all keywords in this call
    """
    resources = add_keywords_impl(customer_id, ad_group_id, keywords, match_type)
    return f"OK: {len(resources)} keyword(s) [{match_type}] added to ad group {ad_group_id}."


@mcp.tool()
def add_campaign_negative_keywords(
    customer_id: str,
    campaign_id: str,
    keywords: list[str],
    match_type: Literal["EXACT", "PHRASE", "BROAD"] = "BROAD",
) -> str:
    """Add campaign-level negative keywords.

    Args:
        customer_id: The customer/account ID without hyphens
        campaign_id: The campaign to receive the negatives
        keywords: Negative keyword texts
        match_type: Match type applied to all negatives in this call
    """
    resources = add_campaign_negative_keywords_impl(
        customer_id, campaign_id, keywords, match_type
    )
    return f"OK: {len(resources)} negative keyword(s) [{match_type}] added to campaign {campaign_id}."


@mcp.tool()
def create_responsive_search_ad(
    customer_id: str,
    ad_group_id: str,
    headlines: list[str],
    descriptions: list[str],
    final_url: str,
    path1: str = "",
    path2: str = "",
) -> str:
    """Create a Responsive Search Ad. Validates lengths before sending (headlines ≤30 chars, descriptions ≤90).

    Args:
        customer_id: The customer/account ID without hyphens
        ad_group_id: The ad group to receive the ad
        headlines: 3 to 15 headlines, each up to 30 characters
        descriptions: 2 to 4 descriptions, each up to 90 characters
        final_url: Landing page URL
        path1: Optional display path segment 1 (up to 15 chars)
        path2: Optional display path segment 2 (up to 15 chars)
    """
    try:
        result = create_responsive_search_ad_impl(
            customer_id, ad_group_id, headlines, descriptions, final_url, path1, path2
        )
    except ValueError as e:
        return f"Error: {e}"
    return f"OK: RSA created in ad group {ad_group_id}. Resource: {result['ad_resource']}"


@mcp.tool()
def set_conversion_action_primary(
    customer_id: str,
    conversion_action_id: str,
    primary: bool,
) -> str:
    """Set whether a conversion action is primary (feeds bidding) or secondary (observation only).

    Args:
        customer_id: The customer/account ID without hyphens
        conversion_action_id: The conversion action ID to update
        primary: True = primary (biddable), False = secondary (observation)
    """
    resource = set_conversion_action_primary_impl(
        customer_id, conversion_action_id, primary
    )
    label = "PRIMARY (feeds bidding)" if primary else "SECONDARY (observation only)"
    return f"OK: Conversion action {conversion_action_id} is now {label}. Resource: {resource}"
