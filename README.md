# Salmon Feed Optimizer

Least-cost formulation of Atlantic salmon feed with linear programming, built on free, sourced data, with the scenario and raw material planning questions a feed company deals with every day. It then tests how often the least-cost recipe actually meets spec when ingredient lots vary, and uses chance-constrained (second-order cone) optimization to price a recipe that does.

![Base recipe](outputs/base_recipe.png)

## What it does

Every batch of salmon feed is a recipe: some fish meal, some soy protein, some rapeseed oil, and so on. The job is to hit the fish's nutritional targets at the lowest cost, using raw materials you can actually get. This project does that and then asks the follow-up questions:

1. **Least-cost recipe.** Finds the cheapest mix of 15 ingredients that meets protein, fat, digestible energy, DP/DE ratio, EPA+DHA, phosphorus, fibre, ash, starch and 10 essential amino acid requirements for two fish sizes.
2. **Why the recipe looks like it does.** Shadow prices show which requirement is costing money, and reduced costs show how far an unused ingredient's price has to fall before it enters.
3. **Price shocks.** Re-optimizes as fish oil moves from 1,500 to 9,000 USD/t and shows where algal oil takes over.
4. **Nutrition targets.** Prices the cost of raising EPA+DHA in the feed.
5. **Supply disruption.** A late fish oil delivery caps what you can use; the model re-formulates around it.
6. **Sustainability.** Caps fish meal plus fish oil and shows the cost of lower forage fish dependency.
7. **Real price history.** Re-optimizes with World Bank prices from 2023 to April 2026.
8. **Benchmarking.** Compares the result with Norway's actual 2020 salmon feed (Nofima) and a measured Skretting commercial feed profile.
9. **Raw material planning.** Turns a recipe and a monthly production plan into tonnage, checks it against stock and inbound deliveries, flags shortfalls and re-formulates within what's available.
10. **Batch variability.** Simulates 10,000 batches with Feedipedia's ingredient standard deviations to see how often the least-cost recipe actually meets spec, and which ingredient causes the spread.
11. **Chance-constrained formulation.** Re-optimizes so each requirement is met in a chosen share of batches (80% to 99.9%), using second-order cone constraints, and prices that reliability.

There is also a small Streamlit app to play with prices, targets, stock and a reliability slider (share of batches that must meet each requirement), with a live batch simulation showing how many batches would meet spec.

## Key results

March 2026 prices, grower feed for 1 to 2 kg fish:

| | Result |
|---|---|
| Raw material cost | **1,105 USD/t** |
| Recipe | Soy protein concentrate 30.6%, rapeseed oil 23.4%, wheat 13.6%, maize gluten 12.0%, fish meal 9.7%, soybean meal 5.0%, fish oil 3.0%, premix and amino acids 2.8% |
| Most expensive constraints | Fibre max (100 USD/t per point), EPA+DHA min (82 USD/t per point), methionine min (21) |
| Smolt feed (100 to 250 g) | 1,167 USD/t, with fish meal rising to 16% |
| EPA+DHA from 1% to 2% | +82 USD/t |
| Fish oil capped at 1% and 30% dearer | +71 USD/t, algal oil fills the gap |
| Fish meal + fish oil capped at 8% | only +10 USD/t |
| Fish oil price at which algal oil wins | about 6,750 USD/t |
| Simulated batches meeting every requirement | **2%** (six binding requirements each fail in 44 to 51% of batches) |
| Each requirement met in 95% of batches | 1,184 USD/t (+80), 75% of batches meet everything |
| 94% of batches meeting everything | 1,224 USD/t (+120), each requirement held at 99% |

![Fish oil sweep](outputs/fish_oil_price_sweep.png)

**The interesting finding.** Fish oil inclusion barely moves as its price rises. That's because it's the cheapest way to meet the EPA+DHA minimum, so the recipe keeps buying just enough of it until algal oil becomes cheaper per gram of omega-3. Cost climbs linearly until that switch, then flattens. The shadow price on EPA+DHA tells the same story from the other side.

**Price history.** With 2023 prices the optimal recipe used 33% fish meal and no soy protein concentrate, because soybean meal (and so SPC) was expensive. By 2025 soy had fallen 32% and the recipe swung to 31% SPC and 10% fish meal. Same model, same nutrition, completely different shopping list. That's why recipes are re-optimized constantly.

![Historical cost](outputs/historical_cost.png)

**Benchmark against reality.** The model uses 12.7% marine ingredients versus 22% in Norway's 2020 average. That gap is honest and useful: the model only has to meet FAO's minimum EPA+DHA of 1%, while commercial feeds target more omega-3 for fish health and fillet quality, and they keep fish meal for palatability and functional reasons the LP doesn't price. Plant protein (48% vs 41%), vegetable oil (23% vs 20%) and carbohydrate (14% vs 13%) land close to the real numbers.

![Benchmark](outputs/benchmark_norway.png)

**Least cost is not the same as reliable.** The optimizer pushes every binding requirement exactly to its limit, assuming each ingredient has its average composition. Real lots vary. Drawing 10,000 batches from Feedipedia's published standard deviations, methionine, fibre, protein, EPA+DHA, lipid and phosphorus each miss spec in roughly half of batches, and only 2% of batches meet all 21 requirements at once. The spread has clear owners: fish oil causes 88% of the EPA+DHA variance, fish meal 69% of phosphorus and 53% of methionine. To meet each requirement in 95% of batches the recipe would need to sit about 1.2 points above the protein minimum and 0.22 points above the EPA+DHA minimum. The chance-constrained model below prices that margin.

![Batch variability](outputs/batch_variability.png)

**What reliability costs.** The chance-constrained model requires each nutrient to be met in a target share of batches. Holding each requirement at 95% costs 80 USD/t more than the least-cost recipe (+7%), and simulation confirms every requirement then passes in about 95% of batches. Because any of the 21 requirements can fail, only 75% of batches meet all of them at once. Getting about 94% of batches fully in spec means holding each at 99%, for +120 USD/t (+11%). The model buys reliability mainly by adding fish meal (9.7% to 16.5% at 95%) and trimming soy protein concentrate, since fish meal's high protein, methionine and phosphorus lift the averages well clear of the limits, even though it is the main source of variance for phosphorus and methionine.

The common shortcut, which simulates the least-cost recipe once, adds 1.645 standard deviations to each requirement and re-runs the LP, is 6 USD/t cheaper but misses its own target. Once the recipe changes, the spreads change too, so methionine passes in only 87% of batches instead of 95%. The chance-constrained model accounts for the recipe's own spread directly.

![Reliability cost](outputs/reliability_cost.png)

Full tables for every scenario are in [`outputs/summary.md`](outputs/summary.md).

## The model

Decision variable: `x_i`, the as-fed share of ingredient `i` in 1 kg of feed.

```
minimise    sum_i  price_i * x_i
subject to  sum_i  x_i = 1
            sum_i  x_i * nutrient_i  >=  requirement * sum_i x_i * dm_i      (dry matter basis, linear)
            sum_i  x_i * DP_i * 10   >=  k * sum_i x_i * DE_i               (DP/DE ratio)
            min_i  <=  x_i  <=  max_i                                       (practical inclusion limits)
            x_i    <=  available_i / production                             (stock, when planning)
```

FAO requirements are on a dry matter basis while recipes are as fed, so requirements are written as linear constraints against the diet's dry matter. Digestible energy and digestible protein come from gross energy and protein times apparent digestibility coefficients.

Solved with PuLP and CBC, which also returns the duals (shadow prices) and reduced costs.

**Chance-constrained version.** Each requirement row above is `sum_i a_i x_i >= 0` with a per-ingredient coefficient `a_i` (for example `n_i - r * dm_i`). When ingredient composition is random and lots are independent, `P(a'x >= 0) >= alpha` becomes

```
mu' x  -  z_alpha * || diag(sigma) x ||_2  >=  0
```

a second-order cone constraint, assuming the blend is roughly normal. `mu` is the average coefficient and `sigma` its standard deviation, estimated by simulating each ingredient from Feedipedia's standard deviations. At alpha = 50% it reduces to the LP. Solved with CVXPY and Clarabel, then every recipe is re-checked by Monte Carlo simulation.

## Data

Every value is tagged **sourced**, **derived** or **assumed** in `data/raw/`. Details and links in [`data/SOURCES.md`](data/SOURCES.md).

| Layer | Used in | Source |
|---|---|---|
| Ingredient composition | `ingredients_raw.csv` | Feedipedia (INRAE, CIRAD, AFZ, FAO) for fish meal, fish oil, soybean meal, maize gluten meal, faba beans, wheat |
| Ingredient variability | `ingredient_variability.csv` | Feedipedia standard deviations for the same six ingredients; SPC, wheat gluten, pea protein, MCP and EPA+DHA spreads assumed |
| Salmon requirements | `requirements.csv` | FAO AFFRIS Atlantic salmon Tables 2 and 9 |
| Prices | `prices.csv`, `price_history.csv` | World Bank Pink Sheet (May 2026) and IndexMundi (March 2026) |
| Real-world benchmark | `benchmarks.csv` | Aas et al. 2022, Nofima (Norway 2020 feed); Mowi Industry Handbook 2026; Skretting Protec profile from the aquacultuR R package; FAO AFFRIS Table 3 |

### Links

**Ingredient composition (Feedipedia)**

- Fish meal, 70% protein: https://feedipedia.org/node/11685
- Fish oil: https://www.feedipedia.org/node/12094
- Soybean meal, 48% protein: https://www.feedipedia.org/node/26068
- Maize gluten meal: https://www.feedipedia.org/node/12288
- Faba bean seeds, low tannin: https://www.feedipedia.org/node/19701
- Wheat grain: https://www.feedipedia.org/node/12754
- EPA+DHA range for fish oil: Roque et al. 2026, Boletín IMARPE 41(1)

**Salmon requirements (FAO AFFRIS)**

- Table 2, nutrient requirements by life stage: https://www.fao.org/fileadmin/user_upload/affris/docs/Atlantic_Salmon/table_2.htm
- Table 9, commercial feed specs by pellet size: https://www.fao.org/fileadmin/user_upload/affris/docs/Atlantic_Salmon/table_9.htm

**Prices**

- World Bank Commodity Price Data (Pink Sheet), May 2026: https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Pink-Sheet-May-2026.pdf
- IndexMundi commodity prices (rapeseed oil, March 2026): https://www.indexmundi.com/commodities/
- Fish oil: no free price series (IFFO prices are members only), so it is an assumption.

**Benchmarks**

- Aas, Åsgård and Ytrestøyl (2022), *Utilization of feed resources in the production of Atlantic salmon in Norway: an update for 2020*, Aquaculture Reports 26:101316: https://doi.org/10.1016/j.aqrep.2022.101316
- Mowi Salmon Farming Industry Handbook 2026
- aquacultuR R package, `feedcomp` dataset (Skretting Protec 4.5 mm): https://github.com/TellAnAx/aquacultuR

**Possible upgrade**

- USDA-ARS / USFWS Fish Ingredient Digestibility Database: https://www.ars.usda.gov/ARSUserFiles/20500500/fish/DigestibilityDatabaseV2016a.xlsx

**Known gaps, stated plainly:**

- There is no free fish oil price series, so fish oil is an assumption that gets stress-tested.
- Most digestibility values are typical salmonid literature values. Feedipedia only has salmonid values for a few feeds. The USDA-ARS Fish Ingredient Digestibility Database would be the next upgrade.
- Soy protein concentrate, wheat gluten and pea protein composition are typical specs, not lab values.
- Feedipedia standard deviations pool many origins, so the batch simulation and the cost of reliability overstate what a single supplier would see. Nutrients are drawn independently, digestibility is held fixed, and the chance constraints hold each requirement separately rather than all of them jointly.
- Stock data in the planning demo is illustrative.

## Run it

Run every command from the project root (the folder with `pyproject.toml`), not from inside `app/`.

### Option 1: uv (recommended)

[uv](https://docs.astral.sh/uv/) creates the virtual environment and installs the pinned dependencies from `uv.lock` automatically.

```bash
uv sync                                     # first time only
uv run python scripts/run_all.py            # writes tables, charts and summary.md to outputs/ (about 30 s)
uv run pytest -q                            # 14 tests: unit conversion, feasibility, limits, monotonicity, caps, variability, chance constraints
uv run streamlit run app/streamlit_app.py   # interactive formulator
```

### Option 2: pip and a virtual environment

macOS / Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/run_all.py
pytest -q
streamlit run app/streamlit_app.py
```

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/run_all.py
pytest -q
streamlit run app/streamlit_app.py
```

If PowerShell refuses to run `Activate.ps1`, either allow local scripts once with `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or skip activation and call the venv directly:

```powershell
.\.venv\Scripts\python.exe scripts/run_all.py
.\.venv\Scripts\streamlit.exe run app/streamlit_app.py
```

### Option 3: without activating, via `python -m`

Works with any interpreter that has the dependencies installed:

```bash
python -m streamlit run app/streamlit_app.py
python -m pytest -q
```

The app opens at http://localhost:8501. Stop it with `Ctrl+C`.



## Project structure

```
data/
  raw/ingredients_raw.csv          composition per ingredient, with source and status columns
  raw/ingredient_variability.csv   standard deviation per ingredient and nutrient (Feedipedia, some assumed)
  raw/requirements.csv             FAO requirement profiles (grower 1-2 kg, smolt 100-250 g)
  raw/prices.csv                   base prices with source and status
  raw/price_history.csv            World Bank prices 2023 to April 2026
  raw/inclusion_limits.csv         practical min/max per ingredient
  raw/benchmarks.csv               Nofima, Mowi, Skretting Protec, FAO formula
  raw/example_stock.csv            illustrative stock for the planning demo
  SOURCES.md                       where every number comes from, with links
src/feedopt/
  data.py          load raw data, convert to an as-fed nutrient matrix
  model.py         the LP, shadow prices, reduced costs, requirement checks
  scenarios.py     price sweeps, requirement sweeps, supply shocks, marine cap, price history
  planning.py      material requirements, shortfalls, availability-aware re-formulation
  uncertainty.py   Monte Carlo batch simulation, compliance rates, variance by ingredient
  robust.py        chance-constrained formulation (CVXPY), reliability curve, fixed margin comparison
  charts.py        static charts
scripts/
  run_all.py       runs every analysis and writes outputs/
app/
  streamlit_app.py interactive formulator with prices, targets, stock and a reliability slider
tests/
  test_model.py    14 tests
notebooks/
  data_exploration.ipynb
docs/
  Aas et al. 2022 (Nofima) benchmark paper, PDF (CC BY-NC-ND 4.0)
outputs/           generated by run_all.py
  summary.md       every scenario's tables in one file
  *.png            charts used in this README
  *.csv            recipes, sweeps, shadow prices, planning, batch compliance, reliability curve
pyproject.toml, uv.lock, requirements.txt   dependencies (uv lock file and pip export)
```

## Where this could go next

- Swap in the USDA-ARS digestibility database and lab-measured composition.
- Multi-period planning: buy now or later given price forecasts and storage limits.
- Several plants and recipes sharing the same constrained raw materials.
- Pull prices automatically from the World Bank and IMF APIs each month.
- Joint chance constraint (all requirements at once, not each separately) and correlated nutrients within an ingredient, using supplier-specific lot data instead of pooled Feedipedia spreads.

## License

Code: MIT. Data: see each source's terms in `data/SOURCES.md`. The Skretting Protec values come from the aquacultuR package (GPL-3) and are cited, not redistributed as a dataset.
