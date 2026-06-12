# LensShop — one-shot builder for the two Search campaigns (2026-06-11)
#
# Creates (PAUSED):
#   1. [SEARCH] Marca — Lensshop          R$5/dia,  Target Impression Share (abs. top, 90%, teto R$2,00)
#   2. [SEARCH] Lentes — Fundo de Funil   R$15/dia, Maximize Clicks (teto CPC R$2,50)
#
# Run from /root/google-ads-mcp with the venv python and .env loaded:
#   set -a; source .env; set +a; venv/bin/python build_lensshop_search.py

import json

from ads_mcp.tools.lensshop_build import (
    create_search_campaign_impl,
    create_ad_group_impl,
    add_keywords_impl,
    add_campaign_negative_keywords_impl,
    create_responsive_search_ad_impl,
)

CUSTOMER_ID = "5521940727"
SITE = "https://www.lensshop.com.br"

summary = {}

# ---------------------------------------------------------------------------
# 1. [SEARCH] Marca — Lensshop
# ---------------------------------------------------------------------------
print(">> Criando campanha de marca...")
brand = create_search_campaign_impl(
    CUSTOMER_ID,
    name="[SEARCH] Marca — Lensshop",
    daily_budget_brl=5.0,
    bidding="TARGET_IMPRESSION_SHARE",
    cpc_ceiling_brl=2.0,
    impression_share_percent=90,
    impression_share_location="ABSOLUTE_TOP_OF_PAGE",
    status="PAUSED",
)
summary["brand_campaign"] = brand
print(f"   campanha {brand['campaign_id']}")

brand_ag = create_ad_group_impl(
    CUSTOMER_ID, brand["campaign_id"], "Marca — Geral"
)
summary["brand_ad_group"] = brand_ag

add_keywords_impl(
    CUSTOMER_ID,
    brand_ag["ad_group_id"],
    [
        "lensshop",
        "lens shop",
        "lensshop lentes",
        "lensshop lentes de contato",
        "loja lensshop",
        "site lensshop",
    ],
    match_type="EXACT",
)
add_keywords_impl(
    CUSTOMER_ID, brand_ag["ad_group_id"], ["lensshop"], match_type="PHRASE"
)
print("   keywords de marca ok")

create_responsive_search_ad_impl(
    CUSTOMER_ID,
    brand_ag["ad_group_id"],
    headlines=[
        "Lensshop | Site Oficial",
        "Lentes de Contato Originais",
        "Entrega Rápida em Todo Brasil",
        "Parcele em Até 12x no Cartão",
        "As Melhores Marcas de Lentes",
        "Compre Online com Segurança",
    ],
    descriptions=[
        "Compre suas lentes de contato no site oficial da Lensshop. Entrega rápida e segura.",
        "Acuvue, Biofinity, Solótica e mais. Lentes originais com garantia.",
        "Lentes com grau, coloridas e descartáveis. Parcele no cartão em até 12x.",
    ],
    final_url=SITE,
    path1="oficial",
)
print("   RSA de marca ok")

# ---------------------------------------------------------------------------
# 2. [SEARCH] Lentes — Fundo de Funil
# ---------------------------------------------------------------------------
print(">> Criando campanha fundo de funil...")
funil = create_search_campaign_impl(
    CUSTOMER_ID,
    name="[SEARCH] Lentes de Contato — Fundo de Funil",
    daily_budget_brl=15.0,
    bidding="MAXIMIZE_CLICKS",
    cpc_ceiling_brl=2.5,
    status="PAUSED",
)
summary["funil_campaign"] = funil
print(f"   campanha {funil['campaign_id']}")

add_campaign_negative_keywords_impl(
    CUSTOMER_ID,
    funil["campaign_id"],
    [
        "gratis",
        "grátis",
        "como colocar",
        "como tirar",
        "como limpar",
        "como usar",
        "o que é",
        "faz mal",
        "sintomas",
        "machuca",
        "curso",
        "vaga",
        "emprego",
        "vencida",
        "usada",
    ],
    match_type="BROAD",
)
print("   negativas ok")

# --- AG1: Comprar Lentes de Contato ---
ag1 = create_ad_group_impl(
    CUSTOMER_ID, funil["campaign_id"], "Comprar Lentes de Contato"
)
summary["funil_ag1"] = ag1
add_keywords_impl(
    CUSTOMER_ID,
    ag1["ad_group_id"],
    [
        "comprar lentes de contato",
        "comprar lente de contato",
        "lentes de contato online",
        "loja de lentes de contato",
        "lentes de contato promoção",
        "lente de contato barata",
        "onde comprar lentes de contato",
    ],
    match_type="PHRASE",
)
create_responsive_search_ad_impl(
    CUSTOMER_ID,
    ag1["ad_group_id"],
    headlines=[
        "Comprar Lentes de Contato",
        "Lentes de Contato Online",
        "Entrega Rápida e Segura",
        "Parcele em Até 12x",
        "Marcas Originais com Garantia",
        "Promoções em Lentes Hoje",
    ],
    descriptions=[
        "Lentes de contato das melhores marcas com entrega para todo o Brasil. Compre online.",
        "Acuvue, Biofinity, Solótica e mais marcas originais com ótimo preço.",
    ],
    final_url=SITE,
    path1="lentes-contato",
)
print("   AG1 ok")

# --- AG2: Lentes com Grau ---
ag2 = create_ad_group_impl(CUSTOMER_ID, funil["campaign_id"], "Lentes com Grau")
summary["funil_ag2"] = ag2
add_keywords_impl(
    CUSTOMER_ID,
    ag2["ad_group_id"],
    [
        "lente de contato com grau",
        "lentes de contato de grau",
        "lente de contato grau online",
        "comprar lente de contato com grau",
        "lente de contato para miopia",
        "lente de contato para astigmatismo",
    ],
    match_type="PHRASE",
)
create_responsive_search_ad_impl(
    CUSTOMER_ID,
    ag2["ad_group_id"],
    headlines=[
        "Lentes de Contato com Grau",
        "Lente com Grau Online",
        "Miopia e Astigmatismo",
        "Entrega em Todo o Brasil",
        "Parcele em Até 12x",
        "Originais com Garantia",
    ],
    descriptions=[
        "Encontre sua lente de contato com grau. Miopia, hipermetropia e astigmatismo.",
        "Compre online com segurança. Lentes originais e entrega rápida para todo o Brasil.",
    ],
    final_url=SITE,
    path1="com-grau",
)
print("   AG2 ok")

# --- AG3: Marcas de Lentes ---
ag3 = create_ad_group_impl(CUSTOMER_ID, funil["campaign_id"], "Marcas de Lentes")
summary["funil_ag3"] = ag3
add_keywords_impl(
    CUSTOMER_ID,
    ag3["ad_group_id"],
    [
        "lentes acuvue",
        "acuvue oasys",
        "lentes biofinity",
        "biofinity",
        "air optix",
        "lentes solotica",
        "solotica",
        "lentes bausch lomb",
        "soflens",
        "lentes alcon",
    ],
    match_type="PHRASE",
)
create_responsive_search_ad_impl(
    CUSTOMER_ID,
    ag3["ad_group_id"],
    headlines=[
        "Acuvue, Biofinity e Air Optix",
        "Lentes das Melhores Marcas",
        "Solótica e Natural Vision",
        "Originais com Garantia",
        "Entrega Rápida no Brasil",
        "Parcele em Até 12x",
    ],
    descriptions=[
        "Lentes de contato originais: Acuvue, Biofinity, Air Optix, Solótica e mais.",
        "Compre sua marca preferida com entrega rápida e parcelamento no cartão.",
    ],
    final_url=SITE,
    path1="marcas",
)
print("   AG3 ok")

print()
print("=== RESUMO ===")
print(json.dumps(summary, indent=2, ensure_ascii=False))
