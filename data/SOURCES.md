# Data sources

Every number in `data/raw/` is tagged in its own file as **sourced**, **derived** or **assumed**. This page lists where the sourced values come from and why the others had to be assumed.

## Ingredient composition (`ingredients_raw.csv`)

Values are stored the way Feedipedia publishes them (dry matter basis, amino acids as % of protein) and converted to an as-fed basis in `src/feedopt/data.py`.

| Ingredient | Source | Status |
|---|---|---|
| Fish meal | Feedipedia, Fish meal type 70 protein: https://feedipedia.org/node/11685 | sourced |
| Fish oil | Feedipedia, Fish oil: https://www.feedipedia.org/node/12094 (gross energy, salmonid energy digestibility 96.4%) | partly sourced |
| Soybean meal | Feedipedia, Soybean meal type 48: https://www.feedipedia.org/node/26068 | sourced |
| Maize gluten meal | Feedipedia, Maize gluten meal: https://www.feedipedia.org/node/12288 (includes salmonid N digestibility 96% and energy digestibility 83%) | sourced |
| Faba beans | Feedipedia, Faba bean seeds low-tannin: https://www.feedipedia.org/node/19701 | sourced |
| Wheat | Feedipedia, Wheat grain: https://www.feedipedia.org/node/12754 | sourced |
| Soy protein concentrate | Typical commercial spec; amino acid profile copied from soybean meal | assumed |
| Wheat gluten | Typical vital wheat gluten spec | assumed |
| Pea protein concentrate | Typical spec (the Feedipedia table at node/7439 could not be retrieved) | assumed |
| Rapeseed oil, algal oil | Standard oil energy values; algal oil EPA+DHA 50% of fat | assumed |
| EPA+DHA in fish oil | 25% of fat, inside the range IMARPE reports for Peruvian anchoveta (EPA 4 to 14%, DHA 8 to 15% of fatty acids): Roque et al. 2026, Boletin IMARPE 41(1) | assumed within a sourced range |
| Crystalline lysine and methionine | Stoichiometric content (78.8% and 99%) | sourced |

**Digestibility.** Feedipedia only publishes salmonid digestibility for a few feeds (fish oil and maize gluten meal are used here). The rest are typical literature values for salmonids. The best free replacement is the USDA-ARS / USFWS Fish Ingredient Digestibility Database (one Excel file, rainbow trout data): https://www.ars.usda.gov/ARSUserFiles/20500500/fish/DigestibilityDatabaseV2016a.xlsx. Swapping it in only means editing the `adc_protein` and `adc_energy` columns.

## Salmon requirements (`requirements.csv`)

- FAO AFFRIS, Atlantic salmon Table 2, nutrient requirements by life stage: https://www.fao.org/fileadmin/user_upload/affris/docs/Atlantic_Salmon/table_2.htm
- FAO AFFRIS, Atlantic salmon Table 9, commercial feed specs by pellet size: https://www.fao.org/fileadmin/user_upload/affris/docs/Atlantic_Salmon/table_9.htm

Notes: the FAO table labels amino acids as "% of dietary protein", but the values only make sense as % of diet, so they are used that way. FAO values draw on studies from before NRC (2011). The starch minimum (pellet binding) and lipid maximum (coating capacity) are practical assumptions.

## Prices (`prices.csv`, `price_history.csv`)

- World Bank Commodity Price Data (Pink Sheet), May 2026 issue: fish meal, soybean meal, soybean oil, maize, US SRW wheat. https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Pink-Sheet-May-2026.pdf
- IndexMundi commodity snapshot, March 2026: rapeseed oil (1,303.90 USD/t). https://www.indexmundi.com/commodities/
- **Fish oil has no free price series** (IFFO prices are members only). It is set at 3,500 USD/t and stress-tested from 1,500 to 9,000 USD/t.
- Soy protein concentrate, maize gluten meal and faba beans are priced as a fixed premium over their base commodity. Wheat gluten, pea protein, algal oil, amino acids, phosphate and premix are assumptions.

## Benchmarks (`benchmarks.csv`)

- Aas, Åsgård and Ytrestøyl (2022), Utilization of feed resources in the production of Atlantic salmon in Norway: an update for 2020. Aquaculture Reports 26:101316 (Nofima). Norway 2020: fish meal 12%, fish oil 10%, plant protein 41%, vegetable oil 20%, carbohydrate 13%, micro 4%, novel 0.4%.
- Mowi Salmon Farming Industry Handbook 2026: fish meal and fish oil shares in 1990 and Mowi's 2025 feed.
- aquacultuR R package (GPL-3), `feedcomp` dataset: measured composition of Skretting Protec 4.5 mm. https://github.com/TellAnAx/aquacultuR
- FAO AFFRIS Atlantic salmon Table 3, example marine grower formula.

## Planning data (`example_stock.csv`)

Fully illustrative stock and inbound tonnages to demonstrate the planning step. Not real company data.
