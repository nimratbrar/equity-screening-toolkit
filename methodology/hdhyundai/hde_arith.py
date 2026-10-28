"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

Arithmetic behind the HDE scenario file (scenarios_hdhyundai.md, not published). All outputs are [inference] built on the cited inputs.
Inputs: hde_series.csv rows (company quarters, backlog, KRW, PPI); assumptions marked ASSUME are not disclosed by the company."""
h1_rev, h1_op = 1036.5 + 1141.8, 258.3 + 287.0            # KRW bn, Q1+Q2 2026 reported results [company filing; press: Sedaily, Asiae]
rev26 = h1_rev * 2.08                                      # ASSUME H2 = 1.08x H1 (growth through the year)
# ===== PLACEHOLDER INPUTS: ILLUSTRATIVE ONLY =====
# Real values must come from your own licensed data (I/B/E/S, Compustat, Capital IQ) or the company's filings.
krw = 1350.0                                               # [placeholder: KRW per USD close at the analysis date]
# ===== END PLACEHOLDER INPUTS =====
print("H1 margin %.1f%%, 2026e revenue %.0f bn" % (h1_op / h1_rev * 100, rev26))
print("backlog cover %.2fx" % (8.49 * krw / rev26))        # USD 8.49bn backlog Jun 2026 [company filing]
# Won +10% vs USD; ASSUME USD revenue 70 to 80%, USD-linked cost 30 to 40% of cost, EBITDA margin 26%
for s, c in ((0.70, 0.30), (0.80, 0.40)):
    dR, dC = 100 * s * -0.10, 74 * c * -0.10
    print("FX: revenue %.1f%%, EBITDA %.1f%% (unhedged, full year)" % (dR, (dR - dC) / 26 * 100))
# Tariff +10 pts (15% back to 25% after 2027); ASSUME US 45 to 48% of sales, 60 to 75% of it shipped from Ulsan, 30 to 60% absorbed
for us, imp, ab in ((0.45, 0.60, 0.3), (0.48, 0.75, 0.6)):
    hit = us * imp * 0.10 * ab * 100
    print("Tariff: cost %.2f%% of revenue, EBITDA %.1f%%" % (hit, -hit / 26 * 100))
# Middle East 11% of Q2 sales [company filing]; 20 to 40% delayed; ASSUME 30% contribution margin
for f in (0.2, 0.4):
    print("Gulf: revenue %.1f%%, EBITDA %.1f%%" % (-11 * f, -11 * f * 0.30 / 26 * 100))
# ABB Power Products EBIT margin [company filing: ABB annual reports 2008, 2012]
print("ABB Power Products EBIT margin 2008 to 2012: %.1f%%" % ((12.4 / 17.7 - 1) * 100))
# US PPI, power and distribution transformers [source: FRED PCU335311335311, https://fred.stlouisfed.org/series/PCU335311335311]
print("PPI transformers: Jul08-Jan09 %.1f%%, Jan12-Jan16 %.1f%%, Dec19-Sep26 %.1f%%" % (
    (215.2 / 239.0 - 1) * 100, (223.1 / 246.8 - 1) * 100, (475.065 / 256.1 - 1) * 100))
