# Connector templates

Header-only files. They contain no data.

- `capiq_export_template.csv`: the toolkit field names a Capital IQ export can be mapped to. In the pipeline
  config, `connectors.capiq.column_map` maps your export's column headers to these names, for example
  `{"ISIN": "isin", "Total Enterprise Value [Latest]": "enterprise_value"}`. Map at least `isin` or `ticker`.
  Unit and currency conventions are whatever your export uses; state them in your config notes.
- `industry_figures_template.csv`: one row per figure you type from an industry report you license
  (for example IBISWorld). `code_type` is `naics`, `gics` or `sic`; `industry_code` is a prefix
  (for example `33592`). `metric` becomes the column `ind_<metric>`. Always fill `source` and `page`.

Copy a template into `inputs/` (git-ignored), fill it there, and never commit the filled copy.
