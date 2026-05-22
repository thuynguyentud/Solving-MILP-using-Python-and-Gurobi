# 📦 Facility Location Optimization with Stochastic Demand using Python & Gurobi

This project is a hands-on implementation of the **Facility Location Problem (FLP)** using Python and the Gurobi optimization solver. The scenarios and data used are based on a case study from the [MITx MicroMasters program in Supply Chain Management](https://micromasters.mit.edu/scm/), module [Supply Chain Design](https://www.edx.org/learn/supply-chain-design/massachusetts-institute-of-technology-supply-chain-design), which I took in 2022. 
However, real-world demand often fluctuates; therefore, optimising for a single deterministic demand point may leave the network unable to serve customers when actual demand is higher than expected.  
The chance-constrained extension forces the model to select a network configuration that is **feasible in at least 95 % of plausible demand scenarios**, providing an explicit, controllable service-level guarantee.

This project is for educational and personal portfolio use only.

---

## 🧠 Problem Definition: Facility Location Problem (FLP)

The **Facility Location Problem (FLP)** is a classic optimization problem in supply chain management. It involves choosing the optimal locations for facilities (e.g., warehouses, distribution centers, plants) and determining product flows to minimize total operational costs while satisfying customer demands and capacity constraints.

In this project, the FLP is formulated as a **mixed-integer linear program (MILP)** with the objective to minimize:
- Fixed costs of opening distribution centers (DCs),
- Variable handling and shipping costs from plants to DCs and from DCs to regional demand points,
- While ensuring all customer demands are met and no DC exceeds its capacity.

---

## 🏭 Case Study:
**New England Root Beer Distributors (NERD)** is a historic beverage company that has grown from a small, family-run root beer maker into a regional leader in the Northeastern United States. Originally operating multiple small plants, NERD consolidated production into a **single modern manufacturing facility in Scranton, Pennsylvania (SCP)** to reduce costs and improve scalability.

### 🚚 Supply Chain Structure
NERD’s current supply chain includes:
- **1 main manufacturing plant** in Scranton, PA; and potential addition of a **second plant** in Bellows Falls, VT (BFP), which could decentralize production
- **5 candidate distribution centers (DCs)** in New England
- **12 regional demand points (RDCs)** that receive shipments from the DCs

![NERD supply chain network](https://github.com/user-attachments/assets/d7d0581d-429f-4967-a62c-36354d45f4f2)

The supply chain operates in two stages:
1. **Inbound logistics**: shipping root beer barrels from plant(s) to DCs.
2. **Outbound logistics**: Local couriers deliver barrels from DCs to RDCs.

---

### ⚠️ Challenges Faced
Despite operational success at the Scranton plant, NERD's **New England distribution network is inefficient and fragmented**, with facilities added over time through mergers and acquisitions rather than design.

NERD management has raised concerns such as:
- Are there too many DCs currently in operation?
- Should the Bellows Falls plant be used to support distribution?
- Are service levels and capacities appropriate under current and future demand?
- Can the overall network cost be reduced through better design?

Read in detail about the case study and relevant data at [The case study file](case_study_file.pdf). This file belongs to Caplice, C. (2016). *New England Root Beer Distributors (NERD4) Case Study*. MITx MicroMasters in Supply Chain Management.

---

### 💡 Solution Approach in This Project

To support decision-making, this project builds a **network design optimization model** to:
- Determine which DCs should remain open (or be closed),
- Optimize the flow of goods from plant(s) to DCs to RDCs,
- Evaluate the cost-effectiveness of using the Bellows Falls plant,
- Ensure customer demand is satisfied without exceeding facility capacities,
- Minimize total system cost, including fixed, variable, and transportation costs.
- **Extend the deterministic model to handle demand uncertainty**, guaranteeing a 95 % service level across stochastic demand scenarios.

---

## 🧩 Main Project Code:

- ✅ **Model the supply chain network** using mathematical programming
- ✅ **Build and solve the deterministic MILP model** with Python and Gurobi
- ✅ **Decide which DCs to open** by running the deterministic model
- ✅ **Generate stochastic demand scenarios** using a truncated Normal distribution (σ = 15 % of base demand, S = 100 scenarios)
- ✅ **Build and solve the Chance-Constrained MILP** via Sample Average Approximation (SAA), enforcing ≥ 95 % demand satisfaction across scenarios

---

## 🚀 Tools Used

- **Python** (data handling & model setup)
- **Gurobi** (optimization solver). This project used a free academic license from [Gurobi Optimizer](https://www.gurobi.com/)

---

## 🧮 Mathematical Model

### Part 1 — Deterministic MILP
This problem is modeled as a Mixed Integer Linear Program (MILP) to determine optimal facility locations, flows, and total cost minimization.

**Sets**
- P: Set of plants
- I: Set of candidate DCs
- J: Set of regional DCs (RDCs)

**Parameters**
- Dⱼ: Weekly demand at RDCⱼ
- Cᵢ: Capacity of DCᵢ (barrels/week)
- fᵢ: Fixed weekly cost of opening DCᵢ
- cᵢⱼ: Cost per barrel from DCᵢ to RDCⱼ (handling + outbound transport)
- vₚᵢ: Cost per barrel from plantₚ to DCᵢ (production + inbound transport)

**Decision Variables**
- yᵢ ∈ {0, 1}: 1 if DCᵢ is opened, 0 otherwise
- xᵢⱼ ≥ 0: Quantity shipped from DCᵢ to RDCⱼ
- zₚᵢ ≥ 0: Quantity shipped from plantₚ to DCᵢ

**Objective Function**: Minimize total weekly cost= ∑ᵢfᵢyᵢ + ∑ᵢ∑ⱼcᵢⱼ.xᵢⱼ + ∑ₚ∑ᵢvₚᵢ.zₚᵢ

**subject to constraints:**
- Demand satisfaction (RDCs): ∑ᵢxᵢⱼ = Dⱼ    ∀ⱼ ∈ J
- DC capacity (only if opened): ∑ⱼ xᵢⱼ ≤ Cᵢ.yᵢ    ∀ᵢ ∈ I
- Flow conservation at DCs (input = output): ∑ₚ zₚᵢ = ∑ⱼ xᵢⱼ    ∀ᵢ ∈ I
- Non-negativity constraints: xᵢⱼ, zₚᵢ ≥ 0  ∀ᵢ ∈ I, ∀ⱼ ∈ J, ∀ₚ ∈ P;   yᵢ ∈ {0, 1} ∀ᵢ ∈ I

To view the model declaration in Python, open the file [Opt_model.py](Opt_model.py)

---

### Part 2 — Chance-Constrained MILP (Stochastic Extension)

#### Uncertainty Model

Real-world weekly demand at each RDC fluctuates around its historical baseline.
Each RDC demand is modelled as:

`Dⱼˢ ~ TruncatedNormal( mean = Dⱼ, σ = 0.15 · Dⱼ, lower = 0 )`

**S = 100** independent scenarios are sampled (`numpy.random.seed(42)`); any negative draw is replaced by 0 (truncation).

#### Two-Stage Structure

| Stage | Timing | Variables | Description |
|-------|--------|-----------|-------------|
| **First (here-and-now)** | Before uncertainty is revealed | `yᵢ` | DC opening decisions — committed once |
| **Second (wait-and-see)** | After each demand scenario is revealed | `xᵢⱼˢ`, `zₚᵢˢ` | Shipment quantities that adapt per scenario |

#### Additional Variables

- `wˢ ∈ {0,1}`: 1 if scenario *s* is **allowed to be violated**
- `slackⱼˢ ≥ 0`: unmet demand at RDC *j* in scenario *s*

#### Objective — Minimise Fixed Cost + Average Variable Cost

`in Σᵢ fᵢ·yᵢ
(1/S) · Σₛ Σᵢ Σⱼ cᵢⱼ·xᵢⱼˢ
(1/S) · Σₛ Σₚ Σᵢ vₚᵢ·zₚᵢˢ`

Fixed costs are paid once; variable costs are **averaged over all scenarios**
(Sample Average Approximation objective = expected cost).

#### Constraints

| # | Constraint | Description |
|---|-----------|-------------|
| C1a | `Σᵢ xᵢⱼˢ + slackⱼˢ ≥ Dⱼˢ`  ∀j,s | Demand covered by deliveries + slack |
| C1b | `slackⱼˢ ≤ M · wˢ`  ∀j,s | Slack nonzero only in violated scenarios |
| C2 | `Σₛ wˢ ≤ ⌊(1−α)·S⌋` | **Service-level constraint**: at most 5 violations (α = 0.95, S = 100) |
| C3 | `Σⱼ xᵢⱼˢ ≤ Cᵢ·yᵢ`  ∀i,s | Capacity per scenario, same DC decision |
| C4 | `Σₚ zₚᵢˢ = Σⱼ xᵢⱼˢ`  ∀i,s | Flow balance per scenario |

To view the full model code, open [Opt_model.py](Opt_model.py).

---


## ✅ Model Results

To view the data handling and model running code, open
[Model_run.ipynb](Model_run.ipynb).

---

### Part 1 — Deterministic Model Results

After solving the deterministic MILP with Gurobi (< 0.03 s to optimality), the model identified the least-cost DC configuration assuming demand equals its historical baseline exactly.

**Key Results:**

| Metric | Value |
|--------|-------|
| **Total Cost** | **68,264.50 $/week** |
| Fixed DC Costs | 20,000.00 $ |
| Inbound Costs | 9,825.00 $ |
| Outbound Costs | 38,439.50 $ |
| **DCs Opened** | **NA, SP, WO** |

**Inbound Shipments (Plant → DC):**

| From | To | Barrels/week |
|------|----|-------------|
| BFP  | NA | 500.0 |
| SCP  | SP | 500.0 |
| SCP  | WO | 1,000.0 |

**Outbound Shipments (DC → RDC):**

| From | To | Barrels/week |
|------|----|-------------|
| NA | BR | 50.0 |
| NA | CO | 80.0 |
| NA | MN | 110.0 |
| NA | NA | 140.0 |
| NA | PO | 120.0 |
| SP | HA | 130.0 |
| SP | NH | 140.0 |
| SP | NL | 30.0 |
| SP | SP | 200.0 |
| WO | BO | 450.0 |
| WO | BR | 10.0 |
| WO | NL | 40.0 |
| WO | PR | 310.0 |
| WO | WO | 190.0 |

✅ All RDC demands fully satisfied. ✅ All DC capacity and flow constraints respected.

---

### Part 2 — Stochastic Model Results (Chance-Constrained MILP)

#### Scenario Statistics (S = 100)

| RDC | Base Demand | Scenario Mean | Scenario Std | Min | Max |
|-----|:-----------:|:-------------:|:------------:|:---:|:---:|
| BO  | 450 | 456.4 | 56.6 | 309.5 | 612.2 |
| BR  |  60 |  59.1 |  8.6 |  42.4 |  82.0 |
| CO  |  80 |  80.1 | 11.9 |  48.6 | 109.4 |
| HA  | 130 | 131.7 | 18.2 |  85.1 | 171.8 |
| MN  | 110 | 110.3 | 15.9 |  69.2 | 151.7 |
| NA  | 140 | 145.2 | 22.8 |  80.2 | 220.9 |
| NH  | 140 | 144.3 | 19.3 | 104.2 | 194.0 |
| NL  |  70 |  70.0 | 10.5 |  48.6 |  95.8 |
| PO  | 120 | 120.3 | 17.8 |  72.3 | 158.4 |
| PR  | 310 | 305.0 | 46.1 | 175.3 | 416.5 |
| SP  | 200 | 198.6 | 31.9 | 102.8 | 292.4 |
| WO  | 190 | 191.2 | 29.5 | 127.0 | 267.5 |

System-wide weekly demand ranges from ~1,850 to ~2,134 barrels across 100 scenarios vs. the 2,000-barrel deterministic baseline.

#### Chance-Constrained Model Key Results (α = 95 %, S = 100)

| Metric | Value |
|--------|-------|
| **Total Cost (SAA avg.)** | **71,203.17 $/week** |
| Fixed DC Costs | 31,000.00 $ |
| Avg Inbound Costs | 9,541.66 $ |
| Avg Outbound Costs | 30,661.51 $ |
| **DCs Opened** | **BO, NA, SP, WO** |
| Scenarios Satisfied | 95 / 100 (95.0 %) ✅ |
| Scenarios Violated | 5 / 100 (5.0 %) |

The model uses its violation budget **exactly at the limit** (5 out of 100 scenarios violated), which is optimal SAA behaviour — tighter than required would increase cost unnecessarily.

---

### Part 3 — Comparison: Deterministic vs. Chance-Constrained

| Metric | Deterministic | Chance-Constrained |
|--------|:-------------:|:------------------:|
| Total Cost ($/week) | 68,264.50 | 71,203.17 |
| Fixed DC Costs ($) | 20,000 | 31,000 |
| Avg Inbound Costs ($) | 9,825.00 | 9,541.66 |
| Avg Outbound Costs ($) | 38,439.50 | 30,661.51 |
| DCs Opened | NA, SP, WO | **BO**, NA, SP, WO |
| Demand Met (base) | 100 % | 100 % |
| Demand Met (≥ 95 % of scenarios) | ❌ Not guaranteed | ✅ 95 % |

**What changed — and why:**

- **An additional DC is opened (BO):** The stochastic model adds the Boston DC (fixed cost +11,000 $/week) to absorb demand peaks that the three-DC deterministic solution cannot handle.
- **Outbound costs drop sharply (−7,778 $/week):** Adding DC BO shortens the average outbound haul to north-east RDCs, reducing per-barrel transport costs even in high-demand scenarios.
- **Net cost premium for robustness: +2,938.67 $/week (~4.3 %):** This is the *price of robustness* — a modest increase to guarantee 95 % service-level compliance under ±15 % demand variability.

---

## 🤝 Project Closing & Collaboration

This project explores a facility location problem using small-scale synthetic data, inspired by academic case studies. It serves as a practical testbed for formulating and solving both deterministic and stochastic optimization problems with Python and Gurobi.

**Feel free to:**
- Comment or open issues to discuss ideas
- Fork and experiment with model extensions
- Collaborate on improvements or real-world applications

I'm always open to feedback, suggestions, or collaboration opportunities — especially in the areas of supply chain analytics, optimization, and data-driven decision making for operation management.
