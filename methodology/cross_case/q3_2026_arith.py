"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

Arithmetic behind the pre-committed quarterly scorecards (one agent scores each line PASS / IN-BETWEEN / FAIL against
thresholds written BEFORE the results). Inputs are public company-filing figures typed from the documents cited on
each line; no database values are used. The scorecard write-up itself is not included in this repository."""

# Amkor, USD thousands [company filing: 8-K EX-99.1 and 10-Q, Q3 2026]
sales_q3_26, sales_q3_25 = 1_990_557, 1_986_968
comp_share_26, comp_share_25 = 0.26, 0.19          # rounded end-market shares
gp_q3_26 = 363_529
debt = 149_502 + 2_317_733                          # ST borrowings + current LTD, LTD
cash = 1_603_015 + 773_181                          # cash + short-term investments
comp26, comp25 = sales_q3_26 * comp_share_26, sales_q3_25 * comp_share_25
lo = sales_q3_26 * 0.255 / (sales_q3_25 * 0.195) - 1
hi = sales_q3_26 * 0.265 / (sales_q3_25 * 0.185) - 1
print(f"AMKR gross margin {gp_q3_26 / sales_q3_26:.2%}")
print(f"AMKR computing y/y {comp26 / comp25 - 1:+.1%} (rounding band {lo:+.1%} to {hi:+.1%})")
print(f"AMKR net debt Sep-26 USD {(debt - cash) / 1e3:,.1f}m (debt {debt / 1e3:,.1f}m, cash+STI {cash / 1e3:,.1f}m)")
print(f"AMKR Q4 guide midpoint USD {(1.90 + 2.00) / 2:.3f}bn")
print(f"AMKR 9M FCF (OCF - PP&E payments) USD {(868_345 - 1_236_806) / 1e3:,.1f}m")

# HD Hyundai Electric, KRW bn / USD m [company filing: DART 20261027800226; IR deck 3Q26]
sales9m, op_q3, sales_q3 = 3_358.2, 284.5, 1_179.9
orders_h1, orders_q3, orders_q2 = 3_237, 980, 1_440
print(f"HDE OP margin {op_q3 / sales_q3:.2%}")
print(f"HDE Q1 orders implied USD {orders_h1 - orders_q2:,}m; 9M orders USD {orders_h1 + orders_q3:,}m "
      f"= {(orders_h1 + orders_q3) / 5_185:.1%} of 5,185 guide; Q4 needed {5_185 - orders_h1 - orders_q3:,}m")
print(f"HDE 9M sales {sales9m / 4_350:.1%} of 4.35tn guide; Q4 needed KRW {4_350 - sales9m:,.1f}bn")
na_orders_usd, na_sales_krw = 451, 447.9            # Q3 2026, deck p.8
for fx in (1_324.3, 1_334, 1_417, 1_450):      # KRW per USD test points [illustrative FX levels]
    print(f"HDE NA book-to-bill at {fx:,.1f} KRW/USD: {na_orders_usd / (na_sales_krw * 1e3 / fx):.2f}")
print(f"HDE NA book-to-bill reaches 1.5 only at {1.5 * na_sales_krw * 1e3 / na_orders_usd:,.0f} KRW/USD")
for fx in (1_324.3,):
    print(f"HDE Q4 order target KRW 1.3-1.4tn = USD {1_300e3 / fx / 1e3:,.2f}-{1_400e3 / fx / 1e3:,.2f}bn at {fx}")
print(f"HDE net cash change Jun->Sep KRW {706.6 - 895.5:+.1f}bn")

# Nexans, EUR m [company filing: Q3 2026 PR p.2, p.8]
print(f"NEX Q3 current/standard sales ratio {2_584.5 / 1_698.2:.2f}; 9M {7_320.5 / 4_946.7:.2f}")
