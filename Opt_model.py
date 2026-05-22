from gurobipy import Model, GRB, quicksum

def build_model(plants, dcs, rdcs, rdc_demand, dc_capacity, 
                dc_fixed_cost, dc_var_cost, plant_var_cost, 
                inbound_cost, outbound_cost):
    """
    Original deterministic model.
    Minimizes total cost subject to exact demand satisfaction.
    """
    model = Model("Facility_Location_Deterministic")
    model.setParam('OutputFlag', 1)

    # ---------- Decision Variables ----------
    # x[i,j]: quantity shipped from DC i to RDC j
    x = model.addVars(dcs, rdcs, name="x", vtype=GRB.CONTINUOUS, lb=0)
    # y[i]: 1 if DC i is opened, 0 otherwise
    y = model.addVars(dcs, name="y", vtype=GRB.BINARY)
    # z[p,i]: quantity shipped from plant p to DC i
    z = model.addVars(plants, dcs, name="z", vtype=GRB.CONTINUOUS, lb=0)

    # ---------- Objective Function ----------
    model.setObjective(
        quicksum(dc_fixed_cost[i] * y[i] for i in dcs) +
        quicksum((dc_var_cost[i] + outbound_cost[i, j]) * x[i, j]
                 for i in dcs for j in rdcs) +
        quicksum((plant_var_cost[p] + inbound_cost[p, i]) * z[p, i]
                 for p in plants for i in dcs),
        GRB.MINIMIZE
    )

    # ---------- Constraints ----------
    # C1: Meet demand at each RDC exactly
    for j in rdcs:
        model.addConstr(
            quicksum(x[i, j] for i in dcs) == rdc_demand[j],
            name=f"Demand_{j}"
        )

    # C2: Capacity at each DC (only if opened)
    for i in dcs:
        model.addConstr(
            quicksum(x[i, j] for j in rdcs) <= dc_capacity[i] * y[i],
            name=f"Capacity_{i}"
        )

    # C3: Flow balance at DC: Inflow = Outflow
    for i in dcs:
        model.addConstr(
            quicksum(z[p, i] for p in plants) == quicksum(x[i, j] for j in rdcs),
            name=f"FlowBalance_{i}"
        )

    return model, x, y, z


def build_chance_constrained_model(plants, dcs, rdcs,
                                   base_demand, demand_scenarios,
                                   dc_capacity, dc_fixed_cost, dc_var_cost,
                                   plant_var_cost, inbound_cost, outbound_cost,
                                   service_level=0.95):
    """
    Chance-Constrained MILP using Sample Average Approximation (SAA).

    Approach:
    ---------
    Instead of requiring demand to be met in ALL scenarios (too conservative)
    or just on average (too risky), we use binary scenario variables:
        - w[s] = 1 if scenario s is VIOLATED (demand NOT fully met)
        - w[s] = 0 if scenario s is SATISFIED

    We allow at most (1 - service_level) fraction of scenarios to be violated.
    This enforces: P(demand satisfied) >= service_level.

    Variables:
    ----------
    x[i,j,s] : shipment from DC i to RDC j under scenario s
    y[i]      : 1 if DC i is opened (here-and-now, scenario-independent)
    z[p,i,s]  : shipment from plant p to DC i under scenario s
    w[s]      : 1 if scenario s is violated (allowed to violate demand)

    The objective uses AVERAGE cost across all scenarios (SAA objective).
    """

    num_scenarios = len(demand_scenarios)
    # Maximum number of scenarios that can be violated
    max_violations = int((1 - service_level) * num_scenarios)
    scenarios = list(range(num_scenarios))

    print(f"\n{'='*55}")
    print(f"  Chance-Constrained Model Configuration")
    print(f"{'='*55}")
    print(f"  Number of scenarios  : {num_scenarios}")
    print(f"  Service level        : {service_level*100:.0f}%")
    print(f"  Max allowed violations: {max_violations} scenarios")
    print(f"{'='*55}\n")

    model = Model("Facility_Location_ChanceConstrained")
    model.setParam('OutputFlag', 1)

    # ---------- Decision Variables ----------

    # FIRST-STAGE (here-and-now): DC opening decisions
    # These are made BEFORE uncertainty is revealed
    y = model.addVars(dcs, name="y", vtype=GRB.BINARY)

    # SECOND-STAGE (wait-and-see): shipment quantities per scenario
    # These adapt to each scenario after demand is revealed
    x = model.addVars(dcs, rdcs, scenarios, name="x",
                      vtype=GRB.CONTINUOUS, lb=0)
    z = model.addVars(plants, dcs, scenarios, name="z",
                      vtype=GRB.CONTINUOUS, lb=0)

    # Scenario violation indicator
    # w[s] = 1 means we ALLOW scenario s to have unmet demand
    w = model.addVars(scenarios, name="w", vtype=GRB.BINARY)

    # Slack variable: unmet demand at RDC j in scenario s
    # This is only used when w[s] = 1 (violated scenario)
    slack = model.addVars(rdcs, scenarios, name="slack",
                          vtype=GRB.CONTINUOUS, lb=0)

    # ---------- Big-M for constraint relaxation ----------
    # When w[s]=1, the demand constraint is relaxed by up to BigM
    BigM = max(max(demand_scenarios[s][j]
                   for s in scenarios
                   for j in rdcs) * 2, 1)

    # ---------- Objective: Average cost across all scenarios ----------
    # Fixed cost is paid once (not per scenario)
    fixed_cost_term = quicksum(dc_fixed_cost[i] * y[i] for i in dcs)

    # Variable costs are averaged across scenarios
    outbound_cost_term = (1.0 / num_scenarios) * quicksum(
        (dc_var_cost[i] + outbound_cost[i, j]) * x[i, j, s]
        for i in dcs for j in rdcs for s in scenarios
    )

    inbound_cost_term = (1.0 / num_scenarios) * quicksum(
        (plant_var_cost[p] + inbound_cost[p, i]) * z[p, i, s]
        for p in plants for i in dcs for s in scenarios
    )

    model.setObjective(
        fixed_cost_term + outbound_cost_term + inbound_cost_term,
        GRB.MINIMIZE
    )

    # ---------- Constraints ----------

    # C1: Demand satisfaction with chance constraint
    # If w[s] = 0: demand must be fully met (sum of x >= demand)
    # If w[s] = 1: constraint relaxed (scenario allowed to violate)
    # Formulation: sum(x[i,j,s]) + slack[j,s] >= demand[j,s]
    #              slack[j,s] <= BigM * w[s]
    for s in scenarios:
        for j in rdcs:
            demand_val = demand_scenarios[s][j]
            # Delivery + slack must cover demand
            model.addConstr(
                quicksum(x[i, j, s] for i in dcs) + slack[j, s] >= demand_val,
                name=f"Demand_s{s}_{j}"
            )
            # Slack is only nonzero if scenario is violated
            model.addConstr(
                slack[j, s] <= BigM * w[s],
                name=f"SlackBound_s{s}_{j}"
            )

    # C2: Service level constraint
    # At most max_violations scenarios can be violated
    model.addConstr(
        quicksum(w[s] for s in scenarios) <= max_violations,
        name="ServiceLevel"
    )

    # C3: DC capacity (scenario-dependent, only if DC is open)
    for s in scenarios:
        for i in dcs:
            model.addConstr(
                quicksum(x[i, j, s] for j in rdcs) <= dc_capacity[i] * y[i],
                name=f"Capacity_s{s}_{i}"
            )

    # C4: Flow balance at each DC for each scenario
    for s in scenarios:
        for i in dcs:
            model.addConstr(
                quicksum(z[p, i, s] for p in plants) ==
                quicksum(x[i, j, s] for j in rdcs),
                name=f"FlowBalance_s{s}_{i}"
            )

    return model, x, y, z, w, slack