"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

Build data/scenario/external/nuclear_series.csv (long format: date, series, value, unit, source).
Hand-entered points are public facts and carry the URL and access date [source: name, date, URL]; FRED series and the
uranium price table are read from files you download yourself into data/scenario/external/ (not included).
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/atkins/build_nuclear_series.py
"""
import csv, re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "data/scenario/external"
A = "accessed 2026-10-20"
rows = []
def add(date, series, value, unit, source):
    rows.append(dict(date=date, series=series, value=value, unit=unit, source=f"{source}, {A}"))

# 1. Uranium prices, month-end spot and long-term (US$/lb U3O8). The original run transcribed the monthly table published at
# https://www.cameco.com/invest/markets/uranium-price . That table is compiled from third-party price reporters, so it is not
# reproduced here: save your own copy as data/scenario/external/uranium_monthly.csv with columns month (YYYY-MM), spot, longterm.
src = "Cameco month-end uranium price table, https://www.cameco.com/invest/markets/uranium-price (your saved copy)"
uf = EXT / "uranium_monthly.csv"
if uf.exists():
    with open(uf) as f:
        for r in csv.DictReader(f):
            add(r["month"] + "-28", "u3o8_spot_usd_lb", r["spot"], "USD/lb", src)
            add(r["month"] + "-28", "u3o8_longterm_usd_lb", r["longterm"], "USD/lb", src)
else:
    print("uranium_monthly.csv not found; uranium price rows skipped")

# 2. Reactor counts
wna = "WNA World Nuclear Power Reactors & Uranium Requirements, updated 16 Oct 2026, https://world-nuclear.org/information-library/facts-and-figures/world-nuclear-power-reactors-and-uranium-requireme.aspx (saved wna_reactors_2026-10-16.html)"
for s, v, u in [("world_reactors_operable", 443, "count"), ("world_capacity_operable", 405667, "MWe net"),
                ("world_reactors_under_construction", 79, "count"), ("world_capacity_under_construction", 86560, "MWe gross"),
                ("world_reactors_planned", 122, "count"), ("world_capacity_planned", 111133, "MWe gross"),
                ("world_reactors_proposed", 336, "count"), ("world_capacity_proposed", 299332, "MWe gross"),
                ("world_uranium_required_2025", 68920, "tU"),
                ("canada_reactors_operable", 17, "count"), ("canada_capacity_operable", 12714, "MWe net"),
                ("canada_reactors_proposed", 20, "count"), ("canada_capacity_proposed", 18464, "MWe gross"),
                ("korea_reactors_operable", 26, "count"), ("korea_reactors_under_construction", 4, "count"),
                ("uk_reactors_operable", 9, "count"), ("uk_reactors_under_construction", 2, "count"),
                ("usa_reactors_operable", 94, "count"), ("usa_reactors_proposed", 25, "count"),
                ("poland_reactors_planned", 7, "count"), ("poland_capacity_planned", 4950, "MWe gross"),
                ("romania_reactors_planned", 8, "count"), ("romania_capacity_planned", 1902, "MWe gross"),
                ("india_reactors_under_construction", 8, "count"), ("china_reactors_under_construction", 38, "count")]:
    add("2026-10-16", s, v, u, wna)
add("2025-05-31", "world_reactors_operable", 439, "count", "Wikipedia list of commercial reactors citing WNA, as of May 2025, https://en.wikipedia.org/wiki/List_of_commercial_nuclear_reactors")
add("2025-05-31", "world_capacity_operable", 397700, "MWe", "Wikipedia list citing WNA, May 2025, same URL")
add("2025-05-31", "world_reactors_under_construction", 68, "count", "Wikipedia list citing WNA, May 2025, same URL")
add("2025-05-31", "world_reactors_planned", 108, "count", "Wikipedia list citing WNA, May 2025, same URL")
add("2026-01-17", "pris_reactors_under_construction", 63, "count", "IAEA PRIS snapshot 2026-01-17 via search result, https://pris.iaea.org/PRIS/WorldStatistics/UnderConstructionReactorsByCountry.aspx")
add("2026-01-17", "pris_capacity_under_construction", 66297, "MWe", "IAEA PRIS snapshot 2026-01-17, same URL")
add("2026-07-17", "pris_reactors_under_construction", 77, "count", "IAEA PRIS snapshot 2026-07-17 via search result, same URL")
add("2026-07-17", "pris_capacity_under_construction", 80720, "MWe", "IAEA PRIS snapshot 2026-07-17, same URL")
add("2025-01-16", "iea_reactors_life_extension_in_progress", 60, "count (about 15% of fleet)", "IEA The Path to a New Era for Nuclear Energy, Jan 2025, via WNN https://world-nuclear-news.org/articles/iea-report-highlights-need-for-new-momentum-behind")
add("2025-01-16", "iea_nuclear_investment_annual", 60, "USD bn (exceeding)", "IEA Path to a New Era, Jan 2025, via engineeringnews.co.za")
add("2026-05-28", "iea_nuclear_investment_annual", 80, "USD bn (exceeding)", "IEA World Energy Investment 2026 via WAM https://www.wam.ae/en/article/c0fuuxe-global-energy-investment-projected-reach-34")
add("2026-05-28", "iea_nuclear_capacity_under_construction", 78, "GW, 15 countries", "IEA WEI 2026 via WAM, same URL")

# 3. Canadian and CANDU project pipeline
add("2016-10-01", "darlington_refurb_budget", 12.8, "CAD bn (4 units, RQE)", "OPG, https://www.opg.com/story/darlington-nuclears-unit-4-returns-to-service-marking-completion-of-refurbishment-project/")
add("2026-02-02", "darlington_refurb_outturn_vs_budget", -150, "CAD m (under budget, 4 months early)", "OPG, same URL; Exchange Monitor 3 Feb 2026")
add("2025-11-30", "pickering_refurb_budget", 26.8, "CAD bn (units 5-8, incl interest, escalation, contingency)", "OPG Feb 2026 https://interactive.opg.com/watts-new/2026-02/opg-set-to-refurbish-pickering-nuclear; Global News Nov 2025")
add("2025-11-30", "pickering_canatom_early_contract", 2.1, "CAD bn (early engineering and procurement, RFR program)", "WNN https://world-nuclear-news.org/articles/pickering-refurbishment-gets-government-go-ahead")
add("2020-01-01", "bruce_mcr_budget", 13.0, "CAD bn (units 3-8, 2020-2033)", "NucNet 4 Feb 2026 https://www.nucnet.org/news/refurbishment-construction-phase-completed-at-canada-s-bruce-3-nuclear-power-plant-2-4-2026")
add("2025-05-08", "darlington_smr_budget_4_units", 20.9, "CAD bn (nominal, incl escalation and financing)", "Globe and Mail / Power Magazine May 2025 https://www.powermag.com/ontario-authorizes-opg-to-start-construction-of-first-commercial-nuclear-smr")
add("2025-05-08", "darlington_smr_unit1_approved", 7.7, "CAD bn (6.1 unit + 1.6 shared)", "Power Magazine May 2025, same URL")
add("2024-12-15", "cernavoda1_refurb_epc", 1.9, "EUR bn (KHNP, Candu Energy, CCC, Ansaldo)", "WNN https://world-nuclear-news.org/articles/first-contract-signed-for-romanian-nuclear-refurbi")
add("2024-11-15", "cernavoda_3_4_epcm", 3.2, "EUR bn (Fluor, AtkinsRealis, Ansaldo, Sargent & Lundy JV)", "WNN https://world-nuclear-news.org/articles/nuclearelectrica-signs-financing-contracts-for-cernavoda-projects")
add("2023-07-05", "bruce_c_capacity", 4800, "MWe (planned, impact assessment to 2028/29)", "IAAC https://www.iaac-aeic.gc.ca/050/evaluations/proj/88771; Yahoo Finance")
add("2026-02-17", "wesleyville_capacity", 10000, "MWe (up to, OPG and Port Hope agreement)", "ANS https://www.ans.org/news/2026-02-17/article-7760/")
add("2025-06-12", "ontario_new_nuclear_need_2050", 17800, "MWe (potential need)", "Ontario ministerial directive 2025-12-11 https://www.ieso.ca/-/media/Files/IESO/Document-Library/corporate/ministerial-directives/Directive-from-the-Minister-of-Energy-and-Mines-20251211-Bruce-C.pdf")
add("2025-06-12", "ontario_demand_growth_2050", 75, "percent (IESO APO 2025, to 262 TWh)", "Torys July 2025 https://www.torys.com/en/our-latest-thinking/publications/2025/07/on-integrated-energy-plan")
add("2012-02-01", "point_lepreau_refurb_overrun", 1.0, "CAD bn over budget, about 3 years late", "CBC 2012 https://amp.cbc.ca/news/canada/new-brunswick/point-lepreau-restart-further-delayed-1.1177867")
add("2026-02-01", "poland_second_plant_tender_year", 2027, "year (competitive procedure)", "NEI https://www.neimagazine.com/news/candu-targets-poland-npp/; Inspenet Feb 2026")

# 4. Policy, uranium supply, macro
add("2026-02-02", "kazatomprom_2026_guidance_100pct", 28250, "tU (mid of 27,500-29,000)", "WNN https://world-nuclear-news.org/articles/kazatomprom-to-lower-uranium-production-in-2026")
add("2026-02-02", "kazatomprom_nominal_capacity_cut", -3080, "tU (32,777 to 29,697)", "WNN, same URL")
add("2026-01-01", "us_russian_leu_waiver_cap_2026", 464183, "kg (waivers end 2028-01-01)", "WNN https://world-nuclear-news.org/articles/doe-unveils-process-for-russian-leu-import-waivers")
add("2026-01-23", "us_office_nuclear_energy_fy2026", 1.685, "USD bn (P.L. 119-74)", "Taxpayers for Common Sense https://www.taxpayer.net/energy-natural-resources/nuclear-power-is-all-the-rage/")
add("2025-10-28", "us_westinghouse_ap1000_programme", 80, "USD bn (at least 8 AP1000, 17.5bn DOE facilities)", "ENR https://www.enr.com/articles/61771-feds-reach-deal-with-westinghouse-for-80b-in-nuclear-reactor-deployments")
add("2025-09-10", "eu_court_taxonomy_nuclear_upheld", 1, "binary", "WNN https://world-nuclear-news.org/articles/nuclear-has-a-place-in-eu-taxonomy-court-rules")
add("2025-07-01", "czech_dukovany_contract", 407, "CZK bn (2 x APR1000, KHNP)", "WNN https://world-nuclear-news.org/articles/khnp-sets-out-plans-for-usd186bn-czech-nuclear-project")
add("2025-09-30", "abacus_canada_nuclear_positive", 38, "percent (22 negative, n=3000)", "Abacus Data https://abacusdata.ca/canadian-public-opinion-on-nuclear-energy/")
add("2023-10-31", "ipsos_canada_nuclear_support", 55, "percent (Ontario 66, Quebec 34)", "Ipsos https://www.ipsos.com/en-ca/over-half-canadians-support-using-nuclear-energy-to-generate-electricity")
add("2026-05-31", "bisconti_us_nuclear_favor", 77, "percent (n=1016)", "Bisconti https://www.bisconti.com/blog/public-opinion-2026")
add("2025-04-30", "gallup_us_nuclear_support", 61, "percent", "Gallup 2025 via WNN")
add("2011-03-15", "cameco_fukushima_one_day_drop", -13, "percent (sector -17%; -25% over first week)", "Motley Fool 15 Mar 2011; CBS News 2011")
add("2011-05-30", "cameco_germany_exit_day_drop", -4.4, "percent", "Globe and Mail https://www.theglobeandmail.com/globe-investor/uranium-miners-slip-on-germanys-nuclear-exit/article581439")

# 5. Engineering services cycle
add("2025-11-04", "canada_budget2025_infrastructure_5yr", 115.2, "CAD bn", "Deloitte / ACEC Canada budget analysis https://acec.ca/advocacy/2025FederalBudget.html")
add("2025-11-04", "canada_infrastructure_bank_envelope", 45, "CAD bn (from 35)", "same")
add("2026-09-30", "iija_extension_expiry", "2026-12-11", "date (P.L. 119-103)", "CRS 14 Sep 2026 https://www.everycrsreport.com/files/2026-09-14_IG10101_7bde9a13a694b6e97925717dcb69733c2b454af8.html")
add("2026-05-17", "build_america_250_act", 580, "USD bn, 5 years (committee 62-2 on 22 May)", "Akin Gump; RCRPC https://www.rcrpc.org/build-america-250-act")
add("2024-12-19", "ofwat_amp8_totex", 104, "GBP bn (2025-30)", "British Water https://www.britishwater.co.uk/news/689672/Ofwat-Announces-Final-Determinations-2025-30.htm")
add("2026-05-31", "hs2_cost_range_low", 87.7, "GBP bn", "HS2 Ltd https://www.hs2.org.uk/hs2-project-update/")
add("2026-05-31", "hs2_cost_range_high", 102.7, "GBP bn", "same")
add("2025-06-11", "uk_defence_gdp_2027_28", 2.6, "percent of GDP", "Institute for Government https://www.instituteforgovernment.org.uk/explainer/uk-defence-spending")
add("2025-06-25", "nato_core_defence_target_2035", 3.5, "percent of GDP", "same")
add("2025-06-11", "uk_sizewell_c_allocation", 14.2, "GBP bn", "Carbon Brief https://www.carbonbrief.org/uk-spending-review-2025-key-climate-and-energy-announcements/")
add("2025-12-31", "saudi_gigaproject_awards", 14.3, "USD bn (-48% y/y after -20% in 2024)", "Enterprise AM 23 Jul 2026 citing MEED https://enterpriseam.com/ksa/2026/07/23/the-gigaproject-slowdown-is-real-and-persisting-through-1h/")
add("2026-06-30", "saudi_gigaproject_awards_h1", 4.5, "USD bn (of 92bn cumulative)", "same")
add("2026-03-31", "saudi_construction_workforce_growth", 6, "percent y/y (32 in 2025, 41 in 2024)", "Salaam Gateway https://salaamgateway.com/story/saudi-construction-hiring-slows-sharply-as-giga-project-ambitions-are-scaled-back")
add("2026-03-31", "pif_capex_change_2026", -15, "percent (expected)", "same")
add("2026-06-30", "acec_canada_backlog_median", 8, "months (US 11)", "ACEC Canada H1 2026 Sentiment Study (saved ACEC_Canada_H12026_Sentiment.pdf) https://acec.ca/files/IndustrySurveys/ACEC_Canada_H12026_Engineering_Business_Sentiment_Study.pdf")
add("2026-06-30", "acec_canada_existing_salary_increase", 5, "percent (from 6)", "same")
add("2026-06-30", "acec_canada_net_rating_firm_finances", 81, "net rating", "same")
add("2026-06-30", "acec_canada_net_rating_industry", 62, "net rating", "same")
add("2026-04-20", "acec_us_backlog_median", 11, "months (n=583)", "ACEC Research Institute Q2 2026 (saved ACEC_US_Q2_2026_Sentiment.pdf)")
add("2026-04-20", "acec_us_inflation_concern_net", 55, "net rating (+21 q/q)", "same")
add("2026-04-20", "acec_us_economy_12m_outlook_net", -6, "net rating", "same")
add("2026-04-20", "acec_us_firms_finding_engineers_difficult", 83, "percent", "same")
add("2026-09-02", "boc_policy_rate", 2.25, "percent", "Bank of Canada 2 Sep 2026 via regalert.today")
add("2026-09-16", "fed_funds_target_upper", 4.00, "percent (hike, two secondary sources)", "tmgm.com UOB note 8 Oct 2026; cryptobriefing")
add("2026-10-12", "brent_usd_bbl", 105.48, "USD/bbl", "Nation Thailand 12 Oct 2026 https://www.nationthailand.com/news/world/40072133")
add("2026-01-15", "wsj_economists_recession_12m", 27, "percent (mean)", "Econbrowser Mar 2026 https://econbrowser.com/archives/2026/03/recession-probabilities-all-around-30f-35")

# 6. FRED series (daily / monthly) already downloaded; take last 2 years of month-ends for compactness
import datetime as dt
def fred(fname, series, unit, sid):
    last = {}
    if not (EXT / fname).exists():
        return print(f"{fname} not found; download it from https://fred.stlouisfed.org/series/{sid}")
    with open(EXT / fname) as f:
        for r in csv.DictReader(f):
            v = r[sid]
            if v in (".", ""): continue
            d = r["observation_date"]
            if d < "2024-01-01": continue
            last[d[:7]] = (d, v)
    for k in sorted(last):
        d, v = last[k]
        add(d, series, v, unit, f"FRED {sid} https://fred.stlouisfed.org/series/{sid} (saved {fname})")
fred("fred_DEXCAUS.csv", "usdcad", "CAD per USD", "DEXCAUS")
fred("fred_DEXUSUK.csv", "gbpusd", "USD per GBP", "DEXUSUK")
fred("fred_DGS10.csv", "us_10y_yield", "percent", "DGS10")
fred("fred_FEDFUNDS.csv", "fed_funds_effective", "percent (monthly avg)", "FEDFUNDS")

out = EXT / "nuclear_series.csv"
with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["date", "series", "value", "unit", "source"])
    w.writeheader(); w.writerows(rows)
print(len(rows), "rows ->", out)
