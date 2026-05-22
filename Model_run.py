# %%
"""
=============================================================
  NERD Case: Deterministic + Chance-Constrained MILP
=============================================================
  Flow:
  1. Load data
  2. Solve deterministic baseline
  3. Generate stochastic demand scenarios
  4. Solve chance-constrained model (95% service level)
  5. Analyze results: scenario satisfaction, cost breakdown
=============================================================
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from Opt_model import build_model, build_chance_constrained_model

# %%
# =============================================================
# SECTION 1: Load Data
# =============================================================
file_path = "D:\\3. study at TUD\\SoSe 25\\7. Gurobi\\NERD_case_data.xlsx"

# na_values=[] and keep_default_na=False prevent "NA" from being
# read as NaN (one DC/RDC is literally named "NA")
rdc_demand_df      = pd.read_excel(file_path, sheet_name="RDC_Demand",
                                   na_values=[], keep_default_na=False)
dc_capacity_df     = pd.read_excel(file_path, sheet_name="DC_Capacity",
                                   na_values=[], keep_default_na=False)
dc_costs_df        = pd.read_excel(file_path, sheet_name="DC_Costs",
                                   na_values=[], keep_default_na=False)
plant_var_cost_df  = pd.read_excel(file_path, sheet_name="Plant_Var_Costs",
                                   na_values=[], keep_default_na=False)
inbound_cost_df    = pd.read_excel(file_path, sheet_name="IB_Costs",
                                   na_values=[], keep_default_na=False)
outbound_cost_df   = pd.read_excel(file_path, sheet_name="OB_Costs",
                                   na_values=[], keep_default_na=False)

print("=== Raw Data Preview ===")
print(rdc_demand_df,     "\n")
print(dc_capacity_df,    "\n")
print(dc_costs_df,       "\n")
print(plant_var_cost_df, "\n")
print(inbound_cost_df,   "\n")
print(outbound_cost_df,  "\n")

# %%
# =============================================================
# SECTION 2: Convert DataFrames to Dictionaries
# =============================================================
rdc_demand     = dict(zip(rdc_demand_df['RDC'],
                          rdc_demand_df['Demand_bl_per_week']))
dc_capacity    = dict(zip(dc_capacity_df['DC'],
                          dc_capacity_df['DC Cap']))
dc_fixed_cost  = dict(zip(dc_costs_df['DC'],
                          dc_costs_df['Fixed Cost']))
dc_var_cost    = dict(zip(dc_costs_df['DC'],
                          dc_costs_df['Var Cost']))
plant_var_cost = dict(zip(plant_var_cost_df['Plant'],
                          plant_var_cost_df['Var Cost']))

# Inbound costs: (plant, dc) -> cost
inbound_cost = {}
for _, row in inbound_cost_df.iterrows():
    dc = row['DC']
    inbound_cost[('BFP', dc)] = row['BFP']
    inbound_cost[('SCP', dc)] = row['SCP']

# Outbound costs: (dc, rdc) -> cost
outbound_cost = {}
for _, row in outbound_cost_df.iterrows():
    dc = row['DC']
    for rdc in outbound_cost_df.columns[1:]:
        outbound_cost[(dc, rdc)] = row[rdc]

# Sanity check
print(f"Spot check outbound_cost[('BO','BR')] = {outbound_cost[('BO','BR')]}")
print(f"  (expected: 51.15)\n")

# Define sets
plants = ['BFP', 'SCP']
dcs    = list(dc_capacity.keys())
rdcs   = list(rdc_demand.keys())

print(f"Plants : {plants}")
print(f"DCs    : {dcs}")
print(f"RDCs   : {rdcs}")

# %%
# =============================================================
# SECTION 3: Solve Deterministic Baseline Model
# =============================================================
print("\n" + "="*55)
print("  STEP 1: Solving Deterministic Baseline Model")
print("="*55)

det_model, x_det, y_det, z_det = build_model(
    plants, dcs, rdcs,
    rdc_demand, dc_capacity, dc_fixed_cost, dc_var_cost,
    plant_var_cost, inbound_cost, outbound_cost
)
det_model.optimize()

if det_model.status == 2:  # Optimal
    print(f"\n{'='*55}")
    print(f"  Deterministic Model: OPTIMAL SOLUTION FOUND")
    print(f"{'='*55}")
    print(f"  Total Cost: {det_model.ObjVal:,.2f}")

    # Cost breakdown
    fixed_det    = sum(dc_fixed_cost[i] * y_det[i].X for i in dcs)
    inbound_det  = sum((plant_var_cost[p] + inbound_cost[(p, i)]) * z_det[p, i].X
                       for p in plants for i in dcs)
    outbound_det = sum((dc_var_cost[i] + outbound_cost[(i, j)]) * x_det[i, j].X
                       for i in dcs for j in rdcs)

    print(f"  Fixed DC Costs  : {fixed_det:>12,.2f}")
    print(f"  Inbound Costs   : {inbound_det:>12,.2f}")
    print(f"  Outbound Costs  : {outbound_det:>12,.2f}")

    print("\n  Opened DCs:")
    for i in dcs:
        if y_det[i].X > 0.5:
            print(f"    ✔ {i}")

    print("\n  Inbound Shipments (Plant → DC):")
    for p in plants:
        for i in dcs:
            if z_det[p, i].X > 1e-4:
                print(f"    {p} → {i}: {z_det[p, i].X:,.1f} barrels")

    print("\n  Outbound Shipments (DC → RDC):")
    for i in dcs:
        for j in rdcs:
            if x_det[i, j].X > 1e-4:
                print(f"    {i} → {j}: {x_det[i, j].X:,.1f} barrels")
else:
    print(f"  Deterministic model status: {det_model.status}")

# %%
# =============================================================
# SECTION 4: Generate Stochastic Demand Scenarios
# =============================================================
print("\n" + "="*55)
print("  STEP 2: Generating Stochastic Demand Scenarios")
print("="*55)

NUM_SCENARIOS   = 50
STD_DEV_FACTOR  = 0.15   # 15% of base demand as standard deviation
RANDOM_SEED     = 42     # For reproducibility

np.random.seed(RANDOM_SEED)

demand_scenarios = []  # List of dicts: [{rdc: demand_value}, ...]

for s in range(NUM_SCENARIOS):
    scenario = {}
    for j in rdcs:
        mean = rdc_demand[j]
        std  = STD_DEV_FACTOR * mean
        # Draw from Normal, then truncate at 0 (no negative demand)
        raw_value      = np.random.normal(loc=mean, scale=std)
        scenario[j]    = max(0.0, raw_value)
    demand_scenarios.append(scenario)

# Display scenario statistics
print(f"\n  Scenario generation parameters:")
print(f"    Scenarios      : {NUM_SCENARIOS}")
print(f"    Std Dev Factor : {STD_DEV_FACTOR*100:.0f}% of base demand")
print(f"    Random Seed    : {RANDOM_SEED}")
print(f"    Truncation     : Negative values forced to 0\n")

print(f"  {'RDC':<8} {'Base Demand':>12} {'Scen Mean':>12} "
      f"{'Scen Std':>10} {'Scen Min':>10} {'Scen Max':>10}")
print(f"  {'-'*64}")
for j in rdcs:
    vals = [demand_scenarios[s][j] for s in range(NUM_SCENARIOS)]
    print(f"  {j:<8} {rdc_demand[j]:>12.1f} {np.mean(vals):>12.1f} "
          f"{np.std(vals):>10.1f} {np.min(vals):>10.1f} {np.max(vals):>10.1f}")

# %%
# =============================================================
# SECTION 5: Visualize Scenario Demand Distribution
# =============================================================
fig, axes = plt.subplots(
    nrows=(len(rdcs) + 3) // 4,
    ncols=4,
    figsize=(16, 3 * ((len(rdcs) + 3) // 4))
)
axes = axes.flatten()

for idx, j in enumerate(rdcs):
    vals = [demand_scenarios[s][j] for s in range(NUM_SCENARIOS)]
    axes[idx].hist(vals, bins=12, color='steelblue', edgecolor='white',
                   alpha=0.8)
    axes[idx].axvline(rdc_demand[j], color='red', linestyle='--',
                      linewidth=1.5, label='Base Demand')
    axes[idx].set_title(f"RDC: {j}", fontsize=9)
    axes[idx].set_xlabel("Demand (barrels)", fontsize=7)
    axes[idx].set_ylabel("Frequency", fontsize=7)
    axes[idx].legend(fontsize=6)
    axes[idx].tick_params(labelsize=7)

# Hide unused subplot panels
for idx in range(len(rdcs), len(axes)):
    axes[idx].set_visible(False)

plt.suptitle(
    f"Demand Scenario Distributions ({NUM_SCENARIOS} scenarios, "
    f"σ = {STD_DEV_FACTOR*100:.0f}% of base demand)",
    fontsize=11, y=1.01
)
plt.tight_layout()
plt.savefig("demand_scenarios.png", dpi=150, bbox_inches='tight')
plt.show()
print("  Figure saved: demand_scenarios.png")

# %%
# =============================================================
# SECTION 6: Solve Chance-Constrained Model
# =============================================================
print("\n" + "="*55)
print("  STEP 3: Solving Chance-Constrained Model (95% SL)")
print("="*55)

SERVICE_LEVEL = 0.95

cc_model, x_cc, y_cc, z_cc, w_cc, slack_cc = build_chance_constrained_model(
    plants, dcs, rdcs,
    rdc_demand,          # base demand (for reference)
    demand_scenarios,    # 50 sampled scenarios
    dc_capacity, dc_fixed_cost, dc_var_cost,
    plant_var_cost, inbound_cost, outbound_cost,
    service_level=SERVICE_LEVEL
)
cc_model.optimize()

# %%
# =============================================================
# SECTION 7: Print Chance-Constrained Results
# =============================================================
if cc_model.status == 2:
    num_scenarios = len(demand_scenarios)
    scenarios     = list(range(num_scenarios))
    max_violations = int((1 - SERVICE_LEVEL) * num_scenarios)

    print(f"\n{'='*55}")
    print(f"  Chance-Constrained Model: OPTIMAL SOLUTION FOUND")
    print(f"{'='*55}")
    print(f"  Total Cost (avg): {cc_model.ObjVal:,.2f}")

    # ---- 7a: Cost Breakdown ----
    fixed_cc    = sum(dc_fixed_cost[i] * y_cc[i].X for i in dcs)
    inbound_cc  = (1.0 / num_scenarios) * sum(
        (plant_var_cost[p] + inbound_cost[(p, i)]) * z_cc[p, i, s].X
        for p in plants for i in dcs for s in scenarios
    )
    outbound_cc = (1.0 / num_scenarios) * sum(
        (dc_var_cost[i] + outbound_cost[(i, j)]) * x_cc[i, j, s].X
        for i in dcs for j in rdcs for s in scenarios
    )
    print(f"\n  Cost Breakdown:")
    print(f"    Fixed DC Costs  : {fixed_cc:>12,.2f}")
    print(f"    Avg Inbound     : {inbound_cc:>12,.2f}")
    print(f"    Avg Outbound    : {outbound_cc:>12,.2f}")

    # ---- 7b: Which DCs are opened ----
    print(f"\n  Opened DCs (Chance-Constrained):")
    opened_dcs_cc = [i for i in dcs if y_cc[i].X > 0.5]
    for i in opened_dcs_cc:
        print(f"    ✔ {i}")

    # ---- 7c: Scenario Analysis ----
    print(f"\n  Scenario Violation Analysis:")
    print(f"  {'Scenario':>10} {'Violated?':>10} "
          f"{'Total Demand':>14} {'Total Delivered':>16} "
          f"{'Total Slack':>12}")
    print(f"  {'-'*65}")

    violated_scenarios   = []
    satisfied_scenarios  = []
    scenario_results     = []  # For DataFrame export

    for s in scenarios:
        is_violated  = w_cc[s].X > 0.5
        total_demand = sum(demand_scenarios[s][j] for j in rdcs)
        total_deliv  = sum(x_cc[i, j, s].X for i in dcs for j in rdcs)
        total_slack  = sum(slack_cc[j, s].X for j in rdcs)

        status_str = "VIOLATED" if is_violated else "OK"
        print(f"  {s:>10} {status_str:>10} "
              f"{total_demand:>14.1f} {total_deliv:>16.1f} "
              f"{total_slack:>12.1f}")

        if is_violated:
            violated_scenarios.append(s)
        else:
            satisfied_scenarios.append(s)

        scenario_results.append({
            'Scenario'       : s,
            'Violated'       : is_violated,
            'Total_Demand'   : total_demand,
            'Total_Delivered': total_deliv,
            'Total_Slack'    : total_slack,
            'Fulfillment_Pct': 100 * total_deliv / total_demand
                               if total_demand > 0 else 100.0
        })

    results_df = pd.DataFrame(scenario_results)

    print(f"\n  Summary:")
    print(f"    Satisfied scenarios : {len(satisfied_scenarios)} / {num_scenarios}")
    print(f"    Violated  scenarios : {len(violated_scenarios)} / {num_scenarios}")
    print(f"    Actual service level: "
          f"{100*len(satisfied_scenarios)/num_scenarios:.1f}%")
    print(f"    Target service level: {SERVICE_LEVEL*100:.0f}%")
    print(f"    Allowed violations  : {max_violations}")
    if violated_scenarios:
        print(f"    Violated scenario IDs: {violated_scenarios}")

    # ---- 7d: Per-RDC demand satisfaction across scenarios ----
    print(f"\n  Per-RDC Average Fulfillment Across All Scenarios:")
    print(f"  {'RDC':<8} {'Base Demand':>12} {'Avg Delivered':>14} "
          f"{'Avg Slack':>10} {'Fulfil%':>8}")
    print(f"  {'-'*55}")
    for j in rdcs:
        avg_del   = np.mean([sum(x_cc[i, j, s].X for i in dcs)
                             for s in scenarios])
        avg_slack = np.mean([slack_cc[j, s].X for s in scenarios])
        avg_dem   = np.mean([demand_scenarios[s][j] for s in scenarios])
        pct       = 100 * avg_del / avg_dem if avg_dem > 0 else 100.0
        print(f"  {j:<8} {rdc_demand[j]:>12.1f} {avg_del:>14.1f} "
              f"{avg_slack:>10.2f} {pct:>7.1f}%")

    # ---- 7e: Average inbound/outbound across scenarios ----
    print(f"\n  Avg Inbound Shipments (Plant → DC) across scenarios:")
    for p in plants:
        for i in dcs:
            avg_z = np.mean([z_cc[p, i, s].X for s in scenarios])
            if avg_z > 1e-4:
                print(f"    {p} → {i}: {avg_z:,.1f} barrels (avg)")

    print(f"\n  Avg Outbound Shipments (DC → RDC) across scenarios:")
    for i in dcs:
        for j in rdcs:
            avg_x = np.mean([x_cc[i, j, s].X for s in scenarios])
            if avg_x > 1e-4:
                print(f"    {i} → {j}: {avg_x:,.1f} barrels (avg)")

else:
    print(f"  Model status: {cc_model.status} (not optimal)")

# %%
# =============================================================
# SECTION 8: Comparison – Deterministic vs Chance-Constrained
# =============================================================
print("\n" + "="*55)
print("  STEP 4: Comparing Deterministic vs Chance-Constrained")
print("="*55)

print(f"\n  {'Metric':<35} {'Deterministic':>14} {'Chance-Constr.':>15}")
print(f"  {'-'*65}")
print(f"  {'Total Cost':<35} {det_model.ObjVal:>14,.2f} "
      f"{cc_model.ObjVal:>15,.2f}")
print(f"  {'Fixed DC Cost':<35} {fixed_det:>14,.2f} {fixed_cc:>15,.2f}")
print(f"  {'Avg Inbound Cost':<35} {inbound_det:>14,.2f} {inbound_cc:>15,.2f}")
print(f"  {'Avg Outbound Cost':<35} {outbound_det:>14,.2f} {outbound_cc:>15,.2f}")

det_opened = [i for i in dcs if y_det[i].X > 0.5]
cc_opened  = [i for i in dcs if y_cc[i].X > 0.5]
print(f"\n  DCs opened (Deterministic)     : {det_opened}")
print(f"  DCs opened (Chance-Constrained): {cc_opened}")

only_in_det = set(det_opened) - set(cc_opened)
only_in_cc  = set(cc_opened)  - set(det_opened)
if only_in_det:
    print(f"  DCs in Deterministic ONLY      : {list(only_in_det)}")
if only_in_cc:
    print(f"  DCs in Chance-Constrained ONLY : {list(only_in_cc)}")
if not only_in_det and not only_in_cc:
    print(f"  Both models open the SAME DCs.")

# %%
# =============================================================
# SECTION 9: Visualizations
# =============================================================

# --- Plot 1: Scenario Fulfillment % ---
fig, ax = plt.subplots(figsize=(14, 5))

colors = ['#d32f2f' if r['Violated'] else '#388e3c'
          for r in scenario_results]

bars = ax.bar(results_df['Scenario'],
              results_df['Fulfillment_Pct'],
              color=colors, edgecolor='white', linewidth=0.5)

ax.axhline(100, color='navy', linestyle='--', linewidth=1.2,
           label='100% fulfillment')
ax.axhline(SERVICE_LEVEL * 100, color='darkorange', linestyle=':',
           linewidth=1.5, label=f'{SERVICE_LEVEL*100:.0f}% service level target')

ax.set_xlabel('Scenario Index', fontsize=11)
ax.set_ylabel('Demand Fulfillment (%)', fontsize=11)
ax.set_title('Demand Fulfillment per Scenario\n'
             '(Chance-Constrained Model, 95% Service Level)',
             fontsize=12)
ax.set_ylim(0, 115)
ax.set_xlim(-0.5, num_scenarios - 0.5)

green_patch = mpatches.Patch(color='#388e3c', label='Satisfied Scenario')
red_patch   = mpatches.Patch(color='#d32f2f', label='Violated Scenario')
ax.legend(handles=[green_patch, red_patch,
                   plt.Line2D([0], [0], color='navy', linestyle='--'),
                   plt.Line2D([0], [0], color='darkorange', linestyle=':')],
          labels=['Satisfied', 'Violated',
                  '100% fulfillment', f'{SERVICE_LEVEL*100:.0f}% target'],
          fontsize=9)

plt.tight_layout()
plt.savefig("scenario_fulfillment.png", dpi=150, bbox_inches='tight')
plt.show()
print("  Figure saved: scenario_fulfillment.png")

# %%
# --- Plot 2: Total Cost Comparison Bar Chart ---
fig, ax = plt.subplots(figsize=(7, 5))

models      = ['Deterministic', 'Chance-Constrained\n(95% SL)']
total_costs = [det_model.ObjVal, cc_model.ObjVal]

bar_colors = ['#1565c0', '#6a1b9a']
bars = ax.bar(models, total_costs, color=bar_colors,
              width=0.45, edgecolor='white')

for bar, val in zip(bars, total_costs):
    ax.text(bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(total_costs) * 0.01,
            f'{val:,.0f}', ha='center', va='bottom', fontsize=10)

ax.set_ylabel('Total Cost', fontsize=11)
ax.set_title('Total Cost: Deterministic vs Chance-Constrained',
             fontsize=11)
ax.set_ylim(0, max(total_costs) * 1.15)
plt.tight_layout()
plt.savefig("cost_comparison.png", dpi=150, bbox_inches='tight')
plt.show()
print("  Figure saved: cost_comparison.png")

# %%
# --- Plot 3: Cost Breakdown Stacked Bar ---
fig, ax = plt.subplots(figsize=(7, 5))

x_pos   = [0, 1]
fixed   = [fixed_det,    fixed_cc]
inbound_vals  = [inbound_det,  inbound_cc]
outbound_vals = [outbound_det, outbound_cc]

b1 = ax.bar(x_pos, fixed,   color='#0288d1', label='Fixed DC Cost')
b2 = ax.bar(x_pos, inbound_vals,  bottom=fixed,
            color='#f57c00', label='Inbound Cost')
b3 = ax.bar(x_pos, outbound_vals,
            bottom=[fixed[k] + inbound_vals[k] for k in range(2)],
            color='#388e3c', label='Outbound Cost')

ax.set_xticks(x_pos)
ax.set_xticklabels(['Deterministic', 'Chance-Constrained\n(95% SL)'])
ax.set_ylabel('Cost', fontsize=11)
ax.set_title('Cost Breakdown Comparison', fontsize=11)
ax.legend(fontsize=9)
plt.tight_layout()
plt.savefig("cost_breakdown.png", dpi=150, bbox_inches='tight')
plt.show()
print("  Figure saved: cost_breakdown.png")

# %%
# =============================================================
# SECTION 10: Export Results to Excel
# =============================================================
output_path = "D:\\3. study at TUD\\SoSe 25\\7. Gurobi\\NERD_results.xlsx"

with pd.ExcelWriter(output_path, engine='openpyxl') as writer:

    # Sheet 1: Scenario results summary
    results_df.to_excel(writer, sheet_name='Scenario_Results', index=False)

    # Sheet 2: DC decisions comparison
    dc_comparison = pd.DataFrame({
        'DC'                : dcs,
        'Det_Open'          : [int(y_det[i].X > 0.5) for i in dcs],
        'CC_Open'           : [int(y_cc[i].X > 0.5)  for i in dcs],
        'Fixed_Cost'        : [dc_fixed_cost[i]       for i in dcs],
        'Capacity'          : [dc_capacity[i]          for i in dcs],
    })
    dc_comparison.to_excel(writer, sheet_name='DC_Decisions', index=False)

    # Sheet 3: Scenario demand table
    scenario_demand_df = pd.DataFrame(demand_scenarios)
    scenario_demand_df.index.name = 'Scenario'
    scenario_demand_df.to_excel(writer, sheet_name='Scenario_Demands')

    # Sheet 4: Cost summary
    cost_summary = pd.DataFrame({
        'Model'       : ['Deterministic', 'Chance-Constrained (95%)'],
        'Total_Cost'  : [det_model.ObjVal, cc_model.ObjVal],
        'Fixed_Cost'  : [fixed_det,  fixed_cc],
        'Inbound_Cost': [inbound_det, inbound_cc],
        'Outbound_Cost':[outbound_det, outbound_cc],
        'Opened_DCs'  : [str(det_opened), str(cc_opened)]
    })
    cost_summary.to_excel(writer, sheet_name='Cost_Summary', index=False)

print(f"\n  Results exported to: {output_path}")
print("\n" + "="*55)
print("  ALL DONE")
print("="*55)