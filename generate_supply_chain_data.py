#!/usr/bin/env python3
"""Generate synthetic reverse supply chain data.

This first version focuses on facility nodes, component definitions, and
starting component inventories. Probabilities in this file are only used for
synthetic data generation; the optimization model should consume the generated
CSV values as deterministic inputs.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import random
import textwrap
from dataclasses import dataclass, field
from pathlib import Path


NODE_TYPES = (
    "customer",
    "local_shop",
    "regional_warehouse",
    "central_depot",
    "specialized_shop",
)

# Component classes correspond to the three-level BOM hierarchy.
COMPONENT_CLASSES = ("lru", "sru", "part")

# Subsystem is currently descriptive metadata. Repair capability is driven by
# numeric difficulty/capability levels, not subsystem-specific specialties.
SUBSYSTEMS = ("avionics", "hydraulics", "propulsion", "landing_gear", "electrical")


@dataclass(frozen=True)
class CountConfig:
    """How many nodes/components to generate."""

    customers: int = 40
    local_shops: int = 12
    regional_warehouses: int = 5
    central_depots: int = 1
    specialized_shops: int = 4
    lrus: int = 8
    srus_per_lru: int = 3
    shared_parts: int = 30
    parts_per_sru: int = 3


@dataclass(frozen=True)
class GeneratorConfig:
    """Configuration for synthetic data generation."""

    # Complexity level controls which optional model features are emitted.
    # Level 0 is the base model: no node repair capacity and no node-specific
    # repair cost. Higher levels can add those features back.
    complexity: int = 0

    # The seed makes output reproducible. Running the script with the same seed
    # and config will generate the same CSV files.
    seed: int = 524

    # Nodes live on a synthetic square map. Distances can later be calculated
    # directly from x-y coordinates.
    coordinate_min: float = 0.0
    coordinate_max: float = 100.0

    # Central depots are generated near the middle of the map so they act like
    # broad network hubs rather than random edge facilities.
    depot_center: tuple[float, float] = (50.0, 50.0)
    depot_spread: float = 8.0
    counts: CountConfig = field(default_factory=CountConfig)

    # Repair capacity is the total number of repair jobs a node can handle in a
    # planning period. Storage is assumed unlimited for now, so it is not listed.
    repair_capacity_ranges: dict[str, tuple[int, int]] = field(
        default_factory=lambda: {
            "customer": (0, 0),
            "local_shop": (5, 25),
            "regional_warehouse": (40, 120),
            "central_depot": (250, 600),
            "specialized_shop": (30, 100),
        }
    )

    # Repair capability is the maximum component difficulty a node can repair.
    # Customers cannot repair anything. Specialized shops are high skill but
    # lower scale than depots.
    repair_capability_ranges: dict[str, tuple[int, int]] = field(
        default_factory=lambda: {
            "customer": (0, 0),
            "local_shop": (1, 3),
            "regional_warehouse": (4, 6),
            "central_depot": (8, 9),
            "specialized_shop": (7, 9),
        }
    )

    # Coverage probability answers: "How likely is this node type to carry at
    # least one unit of this component class?" If a component is covered, the
    # actual quantity is drawn from inventory_quantity_ranges below.
    #
    # These probabilities are NOT model inputs. They are just a recipe for
    # producing deterministic node_inventory.csv values.
    inventory_coverage_probability: dict[str, dict[str, float]] = field(
        default_factory=lambda: {
            "customer": {
                "lru": 0.00,
                "sru": 0.00,
                "part": 0.00,
            },
            "local_shop": {
                "lru": 0.00,
                "sru": 0.15,
                "part": 0.85,
            },
            "regional_warehouse": {
                "lru": 0.05,
                "sru": 0.60,
                "part": 0.90,
            },
            "central_depot": {
                "lru": 0.20,
                "sru": 0.90,
                "part": 0.98,
            },
            "specialized_shop": {
                "lru": 0.00,
                "sru": 0.65,
                "part": 0.75,
            },
        }
    )

    # If a node carries a component, this controls how many units it carries.
    # The ranges are chosen so depots are broad and deep, regional warehouses
    # are moderate, local shops are small, and specialized shops are narrow.
    inventory_quantity_ranges: dict[str, dict[str, tuple[int, int]]] = field(
        default_factory=lambda: {
            "customer": {
                "lru": (0, 0),
                "sru": (0, 0),
                "part": (0, 0),
            },
            "local_shop": {
                "lru": (1, 1),
                "sru": (1, 1),
                "part": (3, 10),
            },
            "regional_warehouse": {
                "lru": (1, 1),
                "sru": (2, 6),
                "part": (8, 28),
            },
            "central_depot": {
                "lru": (1, 2),
                "sru": (4, 12),
                "part": (35, 120),
            },
            "specialized_shop": {
                "lru": (0, 0),
                "sru": (2, 6),
                "part": (12, 45),
            },
        }
    )

    repair_cost_multiplier_by_type: dict[str, float] = field(
        default_factory=lambda: {
            "specialized_shop": 1.40,
            "local_shop": 1.20,
            "regional_warehouse": 1.00,
            "central_depot": 0.85,
        }
    )
    repair_base_cost_by_class: dict[str, int] = field(
        default_factory=lambda: {
            "sru": 18,
            "lru": 24,
        }
    )
    repair_combination_cost_by_child_class: dict[str, float] = field(
        default_factory=lambda: {
            "part": 14.0,
            "sru": 6.0,
        }
    )
    repair_time_multiplier_by_type: dict[str, float] = field(
        default_factory=lambda: {
            "specialized_shop": 0.80,
            "local_shop": 0.95,
            "regional_warehouse": 1.10,
            "central_depot": 1.25,
        }
    )
    repair_base_time_by_class: dict[str, int] = field(
        default_factory=lambda: {
            "sru": 8,
            "lru": 16,
        }
    )
    repair_combination_time_by_child_class: dict[str, float] = field(
        default_factory=lambda: {
            "part": 2.0,
            "sru": 7.0,
        }
    )
    # Arc generation controls. Connections are hierarchical: customers connect
    # to nearby local shops, local shops to regional warehouses, and so on.
    customer_local_connections: int = 2
    local_regional_connections: int = 2
    regional_depot_connections: int = 1
    regional_specialized_connections: int = 1
    specialized_depot_connections: int = 1

    # Demand is generated separately from inventory. Customer nodes have no
    # starting inventory; they create demand for components instead.
    customer_demand_probability: dict[str, float] = field(
        default_factory=lambda: {
            "lru": 0.35,
            "sru": 0.00,
            "part": 0.00,
        }
    )
    customer_demand_quantity_range: dict[str, tuple[int, int]] = field(
        default_factory=lambda: {
            "lru": (1, 3),
            "sru": (0, 0),
            "part": (0, 0),
        }
    )

    # Initial placeholder component-cost ranges. Exported LRU/SRU costs are
    # overwritten from the same BOM-aware formula used by component_multipler.csv.
    # Keeping this draw preserves the seeded structure of existing data sets.
    # Shared final-level PARTs intentionally have no direct component cost.
    component_cost_ranges: dict[str, tuple[int, int] | None] = field(
        default_factory=lambda: {
            "lru": (900, 1500),
            "sru": (150, 500),
            "part": None,
        }
    )
    component_movement_cost_ranges: dict[str, tuple[int, int]] = field(
        default_factory=lambda: {
            "lru": (8, 16),
            "sru": (3, 8),
            "part": (1, 3),
        }
    )

    # A small subset of BOM-used final-level PARTs can only be stocked at specialized
    # shops. This creates a few parts that make specialized shops strategically
    # necessary even in the simple level 0 data.
    specialized_only_part_probability: float = 0.25


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate synthetic reverse supply chain node and inventory data."
    )
    parser.add_argument("--output-dir", default="generated_data")
    parser.add_argument("--seed", type=int, default=524)
    parser.add_argument("--customers", type=int, default=40)
    parser.add_argument("--local-shops", type=int, default=12)
    parser.add_argument("--regional-warehouses", type=int, default=5)
    parser.add_argument("--central-depots", type=int, default=1)
    parser.add_argument("--specialized-shops", type=int, default=4)
    parser.add_argument(
        "--complexity",
        type=int,
        choices=[0, 1, 2, 3],
        default=0,
        help=(
            "Model complexity level. Level 0 omits node repair capacity and "
            "node-specific repair cost. Level 1 adds repair cost, and "
            "Level 2 also adds repair time. Level 3 also adds component "
            "movement cost."
        ),
    )
    parser.add_argument(
        "--components",
        type=int,
        default=80,
        help=(
            "Approximate total component count. The generator converts this "
            "into LRUs, SRUs, and shared PARTs."
        ),
    )
    parser.add_argument(
        "--visualize",
        action="store_true",
        help="Also write a labeled PNG visualization of the generated network.",
    )
    parser.add_argument(
        "--visualization-file",
        default="network_visualization.png",
        help="Visualization filename inside the output directory.",
    )
    parser.add_argument(
        "--visualization-layout",
        choices=["combined", "separate"],
        default="combined",
        help=(
            "Write one combined visualization, or split it into graph, "
            "dependency map, and inventory figures."
        ),
    )
    return parser.parse_args()


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def rounded(value: float) -> float:
    return round(value, 3)


def point_for_node(
    node_type: str,
    idx: int,
    count_for_type: int,
    config: GeneratorConfig,
    rng: random.Random,
) -> tuple[float, float]:
    """Generate x-y coordinates for one node.

    Nodes are placed in loose horizontal bands by echelon. Within each type,
    y-coordinates are evenly spaced with small jitter so nodes do not pile up
    visually, especially customers.
    """

    low = config.coordinate_min
    high = config.coordinate_max
    span = high - low
    x_bands = {
        "customer": (low + 0.03 * span, low + 0.22 * span),
        "local_shop": (low + 0.25 * span, low + 0.42 * span),
        "regional_warehouse": (low + 0.47 * span, low + 0.62 * span),
        "central_depot": (low + 0.70 * span, low + 0.82 * span),
        "specialized_shop": (low + 0.82 * span, low + 0.97 * span),
    }
    band_low, band_high = x_bands[node_type]
    x = rng.uniform(band_low, band_high)

    usable_low = low + 0.08 * span
    usable_high = high - 0.08 * span
    usable_span = usable_high - usable_low
    if count_for_type <= 1:
        y = rng.uniform(usable_low + 0.25 * usable_span, usable_high - 0.25 * usable_span)
    else:
        step = usable_span / (count_for_type - 1)
        base_y = usable_high - (idx - 1) * step
        jitter = rng.uniform(-0.18 * step, 0.18 * step)
        y = base_y + jitter

    return rounded(clamp(x, low, high)), rounded(clamp(y, low, high))


def random_capacity(node_type: str, config: GeneratorConfig, rng: random.Random) -> int:
    """Draw repair capacity from the configured range for this node type."""

    low, high = config.repair_capacity_ranges[node_type]
    if low == high:
        return low
    return rng.randint(low, high)


def random_repair_capability(node_type: str, config: GeneratorConfig, rng: random.Random) -> int:
    """Draw repair capability from the configured range for this node type."""

    low, high = config.repair_capability_ranges[node_type]
    if low == high:
        return low
    return rng.randint(low, high)


def weighted_choice(weights: dict[str, float], rng: random.Random) -> str:
    """Return one label using a dictionary of relative weights."""

    labels = list(weights.keys())
    values = list(weights.values())
    return rng.choices(labels, weights=values, k=1)[0]


def component_count_config_from_total(total_components: int) -> dict[str, int]:
    """Convert an approximate total component count into BOM hierarchy counts."""

    total_components = max(5, total_components)
    lrus = max(1, round(total_components * 0.15))
    srus_per_lru = 2
    shared_parts = max(1, total_components - lrus - (lrus * srus_per_lru))
    parts_per_sru = min(3, shared_parts)
    return {
        "lrus": lrus,
        "srus_per_lru": srus_per_lru,
        "shared_parts": shared_parts,
        "parts_per_sru": parts_per_sru,
    }


def generate_nodes(config: GeneratorConfig, rng: random.Random) -> list[dict[str, object]]:
    """Create all customer and facility nodes."""

    count_by_type = {
        "customer": config.counts.customers,
        "local_shop": config.counts.local_shops,
        "regional_warehouse": config.counts.regional_warehouses,
        "central_depot": config.counts.central_depots,
        "specialized_shop": config.counts.specialized_shops,
    }

    prefix_by_type = {
        "customer": "CUST",
        "local_shop": "LOCAL",
        "regional_warehouse": "REGWH",
        "central_depot": "DEPOT",
        "specialized_shop": "SPEC",
    }

    nodes: list[dict[str, object]] = []
    for node_type in NODE_TYPES:
        for idx in range(1, count_by_type[node_type] + 1):
            x, y = point_for_node(node_type, idx, count_by_type[node_type], config, rng)

            nodes.append(
                {
                    "node_id": f"{prefix_by_type[node_type]}_{idx}",
                    "node_type": node_type,
                    "x": x,
                    "y": y,
                }
            )
            if config.complexity >= 1:
                nodes[-1]["repair_capability"] = random_repair_capability(
                    node_type, config, rng
                )
                nodes[-1]["repair_capacity"] = random_capacity(node_type, config, rng)

    return nodes


def repair_difficulty_for_class(component_class: str, rng: random.Random) -> int:
    """Assign a 1-9 repair difficulty based on component class."""

    if component_class == "part":
        return rng.randint(1, 3)
    if component_class == "sru":
        return rng.randint(4, 6)
    return rng.randint(7, 9)


def component_cost_for_class(
    component_class: str,
    config: GeneratorConfig,
    rng: random.Random,
) -> int | str:
    """Assign component cost by hierarchy level; shared parts have no cost."""

    cost_range = config.component_cost_ranges[component_class]
    if cost_range is None:
        return ""

    low, high = cost_range
    return rng.randint(low, high)


def component_movement_cost_for_class(
    component_class: str,
    config: GeneratorConfig,
    rng: random.Random,
) -> int:
    """Assign intrinsic movement cost by component class."""

    low, high = config.component_movement_cost_ranges[component_class]
    return rng.randint(low, high)


def make_component(
    component_id: str,
    component_class: str,
    indenture_level: int,
    is_shared: int,
    specialized_only: int,
    config: GeneratorConfig,
    rng: random.Random,
) -> dict[str, object]:
    """Create one component row."""

    component = {
        "component_id": component_id,
        "component_class": component_class,
        "subsystem": rng.choice(SUBSYSTEMS),
        "repair_difficulty": repair_difficulty_for_class(component_class, rng),
        "component_cost": component_cost_for_class(component_class, config, rng),
        "indenture_level": indenture_level,
        "is_shared": is_shared,
        "specialized_only": specialized_only,
    }
    return component


def component_sort_key(component_id: object) -> tuple[int, list[int]]:
    """Sort readable component ids in hierarchy order."""

    text = str(component_id)
    if text.startswith("LRU_"):
        return 0, [int(part) for part in text.removeprefix("LRU_").split("_")]
    if text.startswith("PART_"):
        return 1, [int(text.removeprefix("PART_"))]
    return 2, [0]


def generate_components_and_bom(
    config: GeneratorConfig, rng: random.Random
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Create hierarchical components and explicit BOM relationships.

    Level 1 and 2 components use readable hierarchy names:
    LRU_1, LRU_1_1, LRU_1_2, ...

    Level 3 components are shared global PARTs:
    PART_1, PART_2, ...

    Sharing is encoded by reusing the same PART id in multiple BOM rows.
    """

    components: list[dict[str, object]] = []
    bom_rows: list[dict[str, object]] = []

    part_components = [
        make_component(
            f"PART_{idx}",
            "part",
            3,
            1,
            0,
            config,
            rng,
        )
        for idx in range(1, config.counts.shared_parts + 1)
    ]
    components.extend(part_components)
    part_ids = [str(component["component_id"]) for component in part_components]

    for lru_idx in range(1, config.counts.lrus + 1):
        lru_id = f"LRU_{lru_idx}"
        components.append(make_component(lru_id, "lru", 1, 0, 0, config, rng))

        for sru_idx in range(1, config.counts.srus_per_lru + 1):
            sru_id = f"{lru_id}_{sru_idx}"
            components.append(make_component(sru_id, "sru", 2, 0, 0, config, rng))
            bom_rows.append(
                {
                    "parent_component_id": lru_id,
                    "child_component_id": sru_id,
                    "quantity_required": rng.randint(1, 2),
                }
            )

            selected_part_ids = rng.sample(
                part_ids,
                k=min(config.counts.parts_per_sru, len(part_ids)),
            )
            for part_id in selected_part_ids:
                bom_rows.append(
                    {
                        "parent_component_id": sru_id,
                        "child_component_id": part_id,
                        "quantity_required": rng.randint(1, 3),
                    }
                )

    mark_specialized_only_parts(components, bom_rows, config, rng)
    assign_component_repair_costs(components, bom_rows, config)
    if config.complexity >= 3:
        assign_component_movement_costs(components, config)
    components.sort(
        key=lambda row: (int(row["indenture_level"]), component_sort_key(row["component_id"]))
    )
    return components, bom_rows


def mark_specialized_only_parts(
    components: list[dict[str, object]],
    bom_rows: list[dict[str, object]],
    config: GeneratorConfig,
    rng: random.Random,
) -> None:
    """Mark a few BOM-used PARTs as stocked only by specialized shops."""

    component_by_id = {str(component["component_id"]): component for component in components}
    used_part_ids = sorted(
        {
            str(row["child_component_id"])
            for row in bom_rows
            if str(row["child_component_id"]).startswith("PART_")
        },
        key=component_sort_key,
    )
    if not used_part_ids:
        return

    specialized_only_count = max(
        1,
        round(len(used_part_ids) * config.specialized_only_part_probability),
    )
    for part_id in rng.sample(used_part_ids, k=min(specialized_only_count, len(used_part_ids))):
        component_by_id[part_id]["specialized_only"] = 1


def components_used_by_bom(
    components: list[dict[str, object]],
    bom_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return only components that appear in the active BOM relationships."""

    used_component_ids: set[str] = set()
    for row in bom_rows:
        used_component_ids.add(str(row["parent_component_id"]))
        used_component_ids.add(str(row["child_component_id"]))

    return [
        component
        for component in components
        if str(component["component_id"]) in used_component_ids
    ]


def assign_component_repair_costs(
    components: list[dict[str, object]],
    bom_rows: list[dict[str, object]],
    config: GeneratorConfig,
) -> None:
    """Set LRU/SRU component costs to the unmultiplied repair option cost."""

    component_by_id = {str(component["component_id"]): component for component in components}
    children_by_parent: dict[str, list[dict[str, object]]] = {}
    for row in bom_rows:
        children_by_parent.setdefault(str(row["parent_component_id"]), []).append(row)

    for component in components:
        component_class = str(component["component_class"])
        if component_class == "part":
            component["component_cost"] = ""
            continue

        base_repair_cost = config.repair_base_cost_by_class[component_class]
        combination_cost = 0.0
        for child in children_by_parent.get(str(component["component_id"]), []):
            child_component = component_by_id[str(child["child_component_id"])]
            child_class = str(child_component["component_class"])
            quantity_required = int(child["quantity_required"])
            combination_cost += (
                config.repair_combination_cost_by_child_class[child_class]
                * quantity_required
            )

        component["component_cost"] = round(base_repair_cost + combination_cost)


def assign_component_movement_costs(
    components: list[dict[str, object]],
    config: GeneratorConfig,
) -> None:
    """Set component movement costs without perturbing the main data RNG."""

    movement_rng = random.Random(config.seed + 4000)
    for component in components:
        component["movement_cost"] = component_movement_cost_for_class(
            str(component["component_class"]),
            config,
            movement_rng,
        )


def enriched_bom_rows(
    components: list[dict[str, object]],
    bom_rows: list[dict[str, object]],
    config: GeneratorConfig,
) -> list[dict[str, object]]:
    """Add component class and cost details to BOM relationships."""

    component_by_id = {str(component["component_id"]): component for component in components}
    rows: list[dict[str, object]] = []
    for row in bom_rows:
        parent = component_by_id[str(row["parent_component_id"])]
        child = component_by_id[str(row["child_component_id"])]
        enriched_row = {
            "parent_component_id": parent["component_id"],
            "parent_component_class": parent["component_class"],
            "parent_component_cost": parent["component_cost"],
            "child_component_id": child["component_id"],
            "child_component_class": child["component_class"],
            "child_component_cost": child["component_cost"],
            "child_specialized_only": child["specialized_only"],
            "quantity_required": row["quantity_required"],
        }
        if config.complexity >= 3:
            enriched_row["parent_component_movement_cost"] = parent["movement_cost"]
            enriched_row["child_component_movement_cost"] = child["movement_cost"]
        rows.append(enriched_row)
    return rows


def inventory_rule(
    node: dict[str, object], component: dict[str, object], config: GeneratorConfig
) -> tuple[float, tuple[int, int]]:
    """Return the coverage probability and quantity range for one node/component pair."""

    node_type = str(node["node_type"])
    component_class = str(component["component_class"])
    if int(component["specialized_only"]):
        if node_type != "specialized_shop":
            return 0.0, (0, 0)
        return 1.0, config.inventory_quantity_ranges[node_type][component_class]

    return (
        config.inventory_coverage_probability[node_type][component_class],
        config.inventory_quantity_ranges[node_type][component_class],
    )


def generate_inventory(
    nodes: list[dict[str, object]],
    components: list[dict[str, object]],
    config: GeneratorConfig,
    rng: random.Random,
) -> list[dict[str, object]]:
    """Generate the sparse node-component inventory table.

    The output intentionally omits zero-quantity rows. If a node/component pair
    is absent from node_inventory.csv, treat its inventory quantity as zero.
    """

    inventory: list[dict[str, object]] = []

    for node in nodes:
        for component in components:
            coverage_probability, quantity_range = inventory_rule(node, component, config)

            # Flip a weighted coin to decide whether this node stocks this
            # component at all.
            if rng.random() > coverage_probability:
                continue

            low, high = quantity_range
            if high <= 0:
                continue

            # Once the component is stocked, draw a deterministic quantity for
            # the generated CSV instance.
            inventory.append(
                {
                    "node_id": node["node_id"],
                    "component_id": component["component_id"],
                    "quantity": rng.randint(low, high),
                }
            )

    ensure_bom_parts_have_inventory(inventory, nodes, components, config, rng)
    return inventory


def ensure_bom_parts_have_inventory(
    inventory: list[dict[str, object]],
    nodes: list[dict[str, object]],
    components: list[dict[str, object]],
    config: GeneratorConfig,
    rng: random.Random,
) -> None:
    """Guarantee every BOM-used PART appears in at least one valid inventory row."""

    stocked_component_ids = {str(row["component_id"]) for row in inventory}
    part_components = [
        component
        for component in components
        if str(component["component_class"]) == "part"
    ]

    for component in part_components:
        component_id = str(component["component_id"])
        if component_id in stocked_component_ids:
            continue

        if int(component["specialized_only"]):
            candidate_nodes = [
                node for node in nodes if node["node_type"] == "specialized_shop"
            ]
        else:
            candidate_nodes = [
                node for node in nodes if node["node_type"] != "customer"
            ]

        if not candidate_nodes:
            continue

        node = rng.choice(candidate_nodes)
        _, quantity_range = inventory_rule(node, component, config)
        low, high = quantity_range
        if high <= 0:
            continue

        inventory.append(
            {
                "node_id": node["node_id"],
                "component_id": component["component_id"],
                "quantity": rng.randint(low, high),
            }
        )
        stocked_component_ids.add(component_id)


def add_inventory_quantity(
    inventory: list[dict[str, object]],
    node_id: object,
    component_id: object,
    quantity: int,
) -> None:
    """Add quantity to an existing inventory row or create a new one."""

    if quantity <= 0:
        return

    for row in inventory:
        if row["node_id"] == node_id and row["component_id"] == component_id:
            row["quantity"] = int(row["quantity"]) + quantity
            return

    inventory.append(
        {
            "node_id": node_id,
            "component_id": component_id,
            "quantity": quantity,
        }
    )


def inventory_totals_by_component(
    inventory: list[dict[str, object]],
) -> dict[str, int]:
    """Return total inventory by component across all nodes."""

    totals: dict[str, int] = {}
    for row in inventory:
        component_id = str(row["component_id"])
        totals[component_id] = totals.get(component_id, 0) + int(row["quantity"])
    return totals


def bom_leaf_requirements(
    component_id: str,
    quantity: int,
    children_by_parent: dict[str, list[dict[str, object]]],
) -> dict[str, int]:
    """Return bottom-level BOM quantities required for a parent demand."""

    children = children_by_parent.get(component_id, [])
    if not children:
        return {component_id: quantity}

    requirements: dict[str, int] = {}
    for child in children:
        child_id = str(child["child_component_id"])
        child_quantity = quantity * int(child["quantity_required"])
        for required_id, required_quantity in bom_leaf_requirements(
            child_id,
            child_quantity,
            children_by_parent,
        ).items():
            requirements[required_id] = requirements.get(required_id, 0) + required_quantity
    return requirements


def demand_totals_by_component(demand: list[dict[str, object]]) -> dict[str, int]:
    """Return total demand by component across all customers."""

    totals: dict[str, int] = {}
    for row in demand:
        component_id = str(row["component_id"])
        totals[component_id] = totals.get(component_id, 0) + int(row["quantity"])
    return totals


def ensure_demand_can_be_met_through_bom(
    inventory: list[dict[str, object]],
    nodes: list[dict[str, object]],
    components: list[dict[str, object]],
    bom_rows: list[dict[str, object]],
    demand: list[dict[str, object]],
    config: GeneratorConfig,
    rng: random.Random,
) -> None:
    """Guarantee enough leaf PART inventory exists to satisfy LRU demand via BOM."""

    component_by_id = {str(component["component_id"]): component for component in components}
    children_by_parent: dict[str, list[dict[str, object]]] = {}
    for row in bom_rows:
        children_by_parent.setdefault(str(row["parent_component_id"]), []).append(row)

    required_parts: dict[str, int] = {}
    for component_id, quantity in demand_totals_by_component(demand).items():
        for required_id, required_quantity in bom_leaf_requirements(
            component_id,
            quantity,
            children_by_parent,
        ).items():
            component = component_by_id[required_id]
            if str(component["component_class"]) != "part":
                continue
            required_parts[required_id] = required_parts.get(required_id, 0) + required_quantity

    inventory_totals = inventory_totals_by_component(inventory)
    for component_id, required_quantity in sorted(
        required_parts.items(),
        key=lambda item: component_sort_key(item[0]),
    ):
        current_quantity = inventory_totals.get(component_id, 0)
        shortfall = required_quantity - current_quantity
        if shortfall <= 0:
            continue

        component = component_by_id[component_id]
        if int(component["specialized_only"]):
            candidate_nodes = [
                node for node in nodes if node["node_type"] == "specialized_shop"
            ]
        else:
            candidate_nodes = [
                node for node in nodes if node["node_type"] != "customer"
            ]
        if not candidate_nodes:
            continue

        node = rng.choice(candidate_nodes)
        add_inventory_quantity(inventory, node["node_id"], component_id, shortfall)
        inventory_totals[component_id] = current_quantity + shortfall


def generate_demand(
    nodes: list[dict[str, object]],
    components: list[dict[str, object]],
    config: GeneratorConfig,
    rng: random.Random,
) -> list[dict[str, object]]:
    """Generate component demand at customer nodes.

    Demand is separate from inventory. Customer nodes are assumed to start with
    zero inventory, but they can request repair/replacement of components.
    """

    demand: list[dict[str, object]] = []
    customer_nodes = [node for node in nodes if node["node_type"] == "customer"]

    for node in customer_nodes:
        customer_demand_start_index = len(demand)
        for component in components:
            if int(component["indenture_level"]) != 1:
                continue

            component_class = str(component["component_class"])
            demand_probability = config.customer_demand_probability[component_class]
            if rng.random() > demand_probability:
                continue

            low, high = config.customer_demand_quantity_range[component_class]
            demand.append(
                {
                    "demand_id": f"DEMAND_{len(demand) + 1}",
                    "node_id": node["node_id"],
                    "component_id": component["component_id"],
                    "quantity": rng.randint(low, high),
                }
            )

        # Guarantee every customer has at least one demand row. This keeps
        # customer nodes meaningful in small generated instances.
        if len(demand) == customer_demand_start_index:
            top_level_components = [
                component for component in components if int(component["indenture_level"]) == 1
            ]
            component = rng.choice(top_level_components)
            component_class = str(component["component_class"])
            low, high = config.customer_demand_quantity_range[component_class]
            demand.append(
                {
                    "demand_id": f"DEMAND_{len(demand) + 1}",
                    "node_id": node["node_id"],
                    "component_id": component["component_id"],
                    "quantity": rng.randint(low, high),
                }
            )

    return demand


def generate_repair_options(
    nodes: list[dict[str, object]],
    components: list[dict[str, object]],
    bom_rows: list[dict[str, object]],
    config: GeneratorConfig,
) -> list[dict[str, object]]:
    """Generate valid node-component repair choices.

    A repair option exists when the node's repair capability is at least the
    component's repair difficulty. Only LRUs and SRUs are repairable at this
    level; shared PARTs are not emitted as repair options. Customers have
    capability zero, so they will not appear here.
    """

    repair_options: list[dict[str, object]] = []
    component_by_id = {str(component["component_id"]): component for component in components}
    children_by_parent: dict[str, list[dict[str, object]]] = {}
    for row in bom_rows:
        children_by_parent.setdefault(str(row["parent_component_id"]), []).append(row)

    for node in nodes:
        node_type = str(node["node_type"])
        if node_type == "customer":
            continue

        repair_capability = int(node["repair_capability"])
        for component in components:
            if int(component["indenture_level"]) >= 3:
                continue

            repair_difficulty = int(component["repair_difficulty"])
            if repair_capability < repair_difficulty:
                continue

            repair_option = {
                "node_id": node["node_id"],
                "component_id": component["component_id"],
            }
            if config.complexity >= 1:
                cost_multiplier = config.repair_cost_multiplier_by_type[node_type]
                repair_option["repair_cost_multiplier"] = cost_multiplier
                if config.complexity >= 2:
                    component_class = str(component["component_class"])
                    combination_time = 0.0
                    for child in children_by_parent.get(str(component["component_id"]), []):
                        child_component = component_by_id[str(child["child_component_id"])]
                        child_class = str(child_component["component_class"])
                        quantity_required = int(child["quantity_required"])
                        combination_time += (
                            config.repair_combination_time_by_child_class[child_class]
                            * quantity_required
                        )

                    time_multiplier = config.repair_time_multiplier_by_type[node_type]
                    base_repair_time = config.repair_base_time_by_class[component_class]
                    repair_time = max(1, round(base_repair_time + combination_time))
                    repair_option["repair_time"] = repair_time
                    repair_option["repair_time_multiplier"] = time_multiplier
            repair_options.append(repair_option)

    return repair_options


def distance_between(node_a: dict[str, object], node_b: dict[str, object]) -> float:
    """Calculate straight-line Euclidean distance between two nodes."""

    return rounded(
        (
            (float(node_a["x"]) - float(node_b["x"])) ** 2
            + (float(node_a["y"]) - float(node_b["y"])) ** 2
        )
        ** 0.5
    )


def arc_cost_between(node_a: dict[str, object], node_b: dict[str, object]) -> int:
    """Calculate whole-number arc cost from straight-line distance."""

    return round(distance_between(node_a, node_b))


def nearest_nodes(
    source: dict[str, object], candidates: list[dict[str, object]], connection_count: int
) -> list[dict[str, object]]:
    """Return the nearest candidate nodes to one source node."""

    if connection_count <= 0:
        return []

    sorted_candidates = sorted(
        candidates,
        key=lambda candidate: distance_between(source, candidate),
    )
    return sorted_candidates[: min(connection_count, len(sorted_candidates))]


def add_bidirectional_arc_pair(
    arcs: list[dict[str, object]],
    connected_pairs: set[tuple[str, str]],
    node_a: dict[str, object],
    node_b: dict[str, object],
) -> None:
    """Add both travel directions between two nodes if not already present."""

    node_a_id = str(node_a["node_id"])
    node_b_id = str(node_b["node_id"])
    cost = arc_cost_between(node_a, node_b)

    for from_node, to_node in ((node_a_id, node_b_id), (node_b_id, node_a_id)):
        if (from_node, to_node) in connected_pairs:
            continue

        connected_pairs.add((from_node, to_node))
        arcs.append(
            {
                "arc_id": f"ARC_{len(arcs) + 1}",
                "from_node": from_node,
                "to_node": to_node,
                "cost": cost,
            }
        )


def generate_arcs(nodes: list[dict[str, object]], config: GeneratorConfig) -> list[dict[str, object]]:
    """Generate valid node connections in both directions.

    The first arc model is deliberately simple. It creates a layered network and
    assigns cost as straight-line distance. Later, cost can be replaced with
    transport cost, time, capacity, or direction-specific values.
    """

    nodes_by_type = {
        node_type: [node for node in nodes if node["node_type"] == node_type]
        for node_type in NODE_TYPES
    }

    arcs: list[dict[str, object]] = []
    connected_pairs: set[tuple[str, str]] = set()

    connection_rules = (
        ("customer", "local_shop", config.customer_local_connections),
        ("local_shop", "regional_warehouse", config.local_regional_connections),
        ("regional_warehouse", "central_depot", config.regional_depot_connections),
        ("regional_warehouse", "specialized_shop", config.regional_specialized_connections),
        ("specialized_shop", "central_depot", config.specialized_depot_connections),
    )

    for source_type, target_type, connection_count in connection_rules:
        target_nodes = nodes_by_type[target_type]
        for source in nodes_by_type[source_type]:
            for target in nearest_nodes(source, target_nodes, connection_count):
                add_bidirectional_arc_pair(arcs, connected_pairs, source, target)

    return arcs


def simple_node_label_offset(node: dict[str, object], config: GeneratorConfig) -> tuple[int, int, str, str]:
    """Place a node label above, below, left, or right of the marker."""

    x = float(node["x"])
    y = float(node["y"])
    low = config.coordinate_min
    high = config.coordinate_max
    margin = 12

    if y <= low + 12:
        return 0, margin, "center", "bottom"
    if y >= high - 12:
        return 0, -margin, "center", "top"
    if x <= low + 12:
        return margin, 0, "left", "center"
    if x >= high - 12:
        return -margin, 0, "right", "center"
    return 0, margin, "center", "bottom"


def node_label_avoidance_bounds(
    node: dict[str, object],
    config: GeneratorConfig,
) -> tuple[float, float, float, float]:
    """Approximate the data-space rectangle covered by a plotted node label."""

    x = float(node["x"])
    y = float(node["y"])
    label_lines = [str(node["node_id"])]
    if "repair_capability" in node and node["node_type"] != "customer":
        label_lines.append(f"skill={node['repair_capability']}")

    label_width = max(5.0, max(len(line) for line in label_lines) * 0.62)
    label_height = 3.1 * len(label_lines)
    marker_gap = 1.9
    safety_padding = 1.2
    _, _, horizontal_alignment, vertical_alignment = simple_node_label_offset(node, config)

    if horizontal_alignment == "center":
        left = x - (label_width / 2)
        right = x + (label_width / 2)
    elif horizontal_alignment == "left":
        left = x + marker_gap
        right = left + label_width
    else:
        right = x - marker_gap
        left = right - label_width

    if vertical_alignment == "center":
        bottom = y - (label_height / 2)
        top = y + (label_height / 2)
    elif vertical_alignment == "bottom":
        bottom = y + marker_gap
        top = bottom + label_height
    else:
        top = y - marker_gap
        bottom = top - label_height

    return (
        left - safety_padding,
        right + safety_padding,
        bottom - safety_padding,
        top + safety_padding,
    )


def edge_label_position(
    from_node: dict[str, object],
    to_node: dict[str, object],
    position_fraction: float = 0.5,
) -> tuple[float, float]:
    """Return a cost-label position along an edge.

    position_fraction=0.5 is the midpoint. Smaller/larger values move the
    label toward either endpoint while keeping it on the relationship line.
    """

    from_x = float(from_node["x"])
    from_y = float(from_node["y"])
    to_x = float(to_node["x"])
    to_y = float(to_node["y"])
    return (
        from_x + position_fraction * (to_x - from_x),
        from_y + position_fraction * (to_y - from_y),
    )


def point_to_segment_distance(
    point: tuple[float, float],
    segment_start: tuple[float, float],
    segment_end: tuple[float, float],
) -> float:
    """Calculate the shortest distance from a point to a line segment."""

    point_x, point_y = point
    start_x, start_y = segment_start
    end_x, end_y = segment_end
    dx = end_x - start_x
    dy = end_y - start_y
    segment_length_squared = dx * dx + dy * dy

    if segment_length_squared == 0:
        return math.hypot(point_x - start_x, point_y - start_y)

    projection = (
        ((point_x - start_x) * dx + (point_y - start_y) * dy)
        / segment_length_squared
    )
    projection = clamp(projection, 0.0, 1.0)
    closest_x = start_x + projection * dx
    closest_y = start_y + projection * dy
    return math.hypot(point_x - closest_x, point_y - closest_y)


def point_to_bounds_distance(
    point: tuple[float, float],
    bounds: tuple[float, float, float, float],
) -> float:
    """Calculate distance from a point to an axis-aligned rectangle."""

    point_x, point_y = point
    left, right, bottom, top = bounds
    dx = max(left - point_x, 0.0, point_x - right)
    dy = max(bottom - point_y, 0.0, point_y - top)
    return math.hypot(dx, dy)


def best_edge_label_position(
    relationship_key: frozenset[str],
    relationship_segments: dict[frozenset[str], tuple[dict[str, object], dict[str, object]]],
    node_label_bounds: list[tuple[float, float, float, float]],
) -> tuple[float, float]:
    """Choose a clear cost-label location on a relationship line.

    The label stays on its own line. If the midpoint is close to another line,
    another node label, or both, this tries several positions closer to either
    endpoint and picks the one with the most clearance.
    """

    from_node, to_node = relationship_segments[relationship_key]
    candidates = (0.50, 0.42, 0.58, 0.34, 0.66, 0.26, 0.74, 0.18, 0.82)
    best_position = edge_label_position(from_node, to_node, candidates[0])
    best_score = -1.0

    other_segments = [
        segment
        for key, segment in relationship_segments.items()
        if key != relationship_key
    ]

    for candidate in candidates:
        position = edge_label_position(from_node, to_node, candidate)

        nearest_other_line = float("inf")
        if other_segments:
            nearest_other_line = min(
                point_to_segment_distance(
                    position,
                    (float(other_start["x"]), float(other_start["y"])),
                    (float(other_end["x"]), float(other_end["y"])),
                )
                for other_start, other_end in other_segments
            )

        nearest_node_label = float("inf")
        if node_label_bounds:
            nearest_node_label = min(
                point_to_bounds_distance(position, bounds)
                for bounds in node_label_bounds
            )

        # Prefer the midpoint when it is similarly clear, so labels stay
        # visually centered unless there is a real overlap problem.
        midpoint_penalty = abs(candidate - 0.5) * 0.5
        score = min(nearest_other_line, nearest_node_label * 1.4) - midpoint_penalty
        if score > best_score:
            best_score = score
            best_position = position

    return best_position


def sorted_relationship_nodes(
    relationship_key: frozenset[str],
    node_by_id: dict[str, dict[str, object]],
) -> tuple[dict[str, object], dict[str, object]]:
    """Return a stable endpoint order for a relationship key."""

    from_node_id, to_node_id = sorted(relationship_key)
    return node_by_id[from_node_id], node_by_id[to_node_id]


def bom_tree_lines(
    components: list[dict[str, object]],
    bom_rows: list[dict[str, object]],
) -> list[str]:
    """Build a compact text tree of LRU/SRU/PART dependencies."""

    component_by_id = {str(row["component_id"]): row for row in components}
    children_by_parent: dict[str, list[dict[str, object]]] = {}
    for row in bom_rows:
        children_by_parent.setdefault(str(row["parent_component_id"]), []).append(row)

    def sort_child(row: dict[str, object]) -> tuple[int, list[int]]:
        return component_sort_key(row["child_component_id"])

    top_level_ids = [
        str(row["component_id"])
        for row in components
        if int(row["indenture_level"]) == 1
    ]
    top_level_ids.sort(key=component_sort_key)

    lines: list[str] = []
    for lru_id in top_level_ids:
        lines.append(lru_id)
        sru_rows = sorted(children_by_parent.get(lru_id, []), key=sort_child)
        for sru_index, sru_row in enumerate(sru_rows):
            sru_id = str(sru_row["child_component_id"])
            sru_prefix = "`--" if sru_index == len(sru_rows) - 1 else "|--"
            lines.append(
                f"{sru_prefix} {sru_id} x{sru_row['quantity_required']}"
            )

            part_rows = sorted(children_by_parent.get(sru_id, []), key=sort_child)
            for part_index, part_row in enumerate(part_rows):
                part_id = str(part_row["child_component_id"])
                part_prefix = "    `--" if part_index == len(part_rows) - 1 else "    |--"
                shared_marker = "*" if int(component_by_id[part_id]["is_shared"]) else ""
                specialized_marker = (
                    "[S]" if int(component_by_id[part_id]["specialized_only"]) else ""
                )
                lines.append(
                    f"{part_prefix} {part_id}{shared_marker}{specialized_marker} x{part_row['quantity_required']}"
                )

    return lines


def visualization_maps(
    nodes: list[dict[str, object]],
    inventory: list[dict[str, object]],
    demand: list[dict[str, object]],
) -> tuple[dict[str, dict[str, object]], dict[str, list[str]], dict[str, list[str]]]:
    """Build shared lookup maps for visualization."""

    node_by_id = {str(node["node_id"]): node for node in nodes}
    inventory_by_node: dict[str, list[str]] = {str(node["node_id"]): [] for node in nodes}
    for row in inventory:
        inventory_by_node[str(row["node_id"])].append(
            f"{row['component_id']}:{row['quantity']}"
        )
    demand_by_node: dict[str, list[str]] = {str(node["node_id"]): [] for node in nodes}
    for row in demand:
        demand_by_node[str(row["node_id"])].append(
            f"{row['component_id']}:{row['quantity']}"
        )
    return node_by_id, inventory_by_node, demand_by_node


def draw_bom_axis(axis: object, components: list[dict[str, object]], bom_rows: list[dict[str, object]]) -> None:
    """Draw the component dependency map on an axis."""

    axis.axis("off")
    axis.set_title(
        "Component Dependency Map (* = shared, [S] = specialized-only)",
        loc="left",
        fontsize=10,
    )
    axis.text(
        0.0,
        1.0,
        "\n".join(bom_tree_lines(components, bom_rows)),
        transform=axis.transAxes,
        family="monospace",
        fontsize=9.75,
        va="top",
        ha="left",
    )


def draw_inventory_axes(
    inventory_axis: object,
    demand_axis: object,
    nodes: list[dict[str, object]],
    inventory_by_node: dict[str, list[str]],
    demand_by_node: dict[str, list[str]],
) -> None:
    """Draw facility inventory and customer demand tables."""

    inventory_axis.axis("off")
    inventory_axis.set_title("Facility Inventory", loc="left", fontsize=10)
    demand_axis.axis("off")
    demand_axis.set_title("Customer Demand", loc="left", fontsize=10)

    inventory_table_rows = []
    for node in nodes:
        if node["node_type"] == "customer":
            continue

        node_id = str(node["node_id"])
        items = sorted(inventory_by_node[node_id])

        component_text = ", ".join(items)
        if not component_text:
            component_text = "none"

        wrapped_component_text = textwrap.fill(
            component_text,
            width=62,
            break_long_words=False,
            break_on_hyphens=False,
        )
        inventory_table_rows.append([node_id, str(node["node_type"]), wrapped_component_text])

    demand_table_rows = []
    for node in nodes:
        if node["node_type"] != "customer":
            continue

        node_id = str(node["node_id"])
        items = sorted(demand_by_node[node_id])
        demand_text = ", ".join(items)
        if not demand_text:
            demand_text = "none"

        wrapped_demand_text = textwrap.fill(
            demand_text,
            width=30,
            break_long_words=False,
            break_on_hyphens=False,
        )
        demand_table_rows.append([node_id, wrapped_demand_text])

    inventory_table = inventory_axis.table(
        cellText=inventory_table_rows,
        colLabels=["node", "type", "inventory"],
        bbox=[0.0, 0.0, 1.0, 0.92],
        cellLoc="left",
        colLoc="left",
        colWidths=[0.16, 0.22, 0.90],
    )
    inventory_table.auto_set_font_size(False)
    inventory_table.set_fontsize(6.5)
    inventory_table.scale(1.0, 1.75)

    # Matplotlib tables do not auto-grow rows for newline-wrapped text, so make
    # each data row taller when its component list uses multiple lines.
    base_cell_height = inventory_table[(1, 0)].get_height() if inventory_table_rows else 0.04
    for row_idx, row in enumerate(inventory_table_rows, start=1):
        line_count = max(cell.count("\n") + 1 for cell in row)
        for col_idx in range(3):
            inventory_table[(row_idx, col_idx)].set_height(
                base_cell_height * max(1.55, 1.35 * line_count)
            )

    demand_table = demand_axis.table(
        cellText=demand_table_rows,
        colLabels=["customer", "demand"],
        bbox=[0.0, 0.0, 1.0, 0.92],
        cellLoc="left",
        colLoc="left",
        colWidths=[0.23, 0.77],
    )
    demand_table.auto_set_font_size(False)
    demand_table.set_fontsize(6.5)
    demand_table.scale(1.0, 1.70)

    base_cell_height = demand_table[(1, 0)].get_height() if demand_table_rows else 0.04
    for row_idx, row in enumerate(demand_table_rows, start=1):
        line_count = max(cell.count("\n") + 1 for cell in row)
        for col_idx in range(2):
            demand_table[(row_idx, col_idx)].set_height(
                base_cell_height * max(1.50, 1.30 * line_count)
            )


def markdown_escape_cell(value: object) -> str:
    """Escape basic Markdown table syntax inside a cell."""

    return str(value).replace("|", "\\|").replace("\n", "<br>")


def markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    """Build a GitHub-flavored Markdown table."""

    lines = [
        "| " + " | ".join(markdown_escape_cell(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(markdown_escape_cell(cell) for cell in row) + " |")
    return "\n".join(lines)


def write_dependency_map_markdown(
    path: Path,
    components: list[dict[str, object]],
    bom_rows: list[dict[str, object]],
) -> None:
    """Write the dependency map as Markdown."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# Component Dependency Map",
                "",
                "`*` marks a shared final-level part. `[S]` marks a specialized-only part.",
                "",
                "```text",
                "\n".join(bom_tree_lines(components, bom_rows)),
                "```",
                "",
            ]
        )
    )


def write_inventory_markdown(
    path: Path,
    nodes: list[dict[str, object]],
    inventory_by_node: dict[str, list[str]],
    demand_by_node: dict[str, list[str]],
) -> None:
    """Write facility inventory and customer demand as Markdown tables."""

    inventory_rows = []
    for node in nodes:
        if node["node_type"] == "customer":
            continue

        node_id = str(node["node_id"])
        inventory_rows.append(
            [
                node_id,
                str(node["node_type"]),
                ", ".join(sorted(inventory_by_node[node_id])) or "none",
            ]
        )

    demand_rows = []
    for node in nodes:
        if node["node_type"] != "customer":
            continue

        node_id = str(node["node_id"])
        demand_rows.append(
            [
                node_id,
                ", ".join(sorted(demand_by_node[node_id])) or "none",
            ]
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n\n".join(
            [
                "# Inventory And Demand",
                "## Facility Inventory",
                markdown_table(["node", "type", "inventory"], inventory_rows),
                "## Customer Demand",
                markdown_table(["customer", "demand"], demand_rows),
                "",
            ]
        )
    )


def write_cost_formula_markdown(path: Path, config: GeneratorConfig) -> None:
    """Write the repair cost/time setup as Markdown."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if config.complexity < 1:
        path.write_text(
            "\n".join(
                [
                    "# Repair Cost Formula",
                    "",
                    "Repair cost is not generated at `--complexity 0`.",
                    "",
                ]
            )
        )
        return

    include_time = config.complexity >= 2
    title = "Repair Cost And Time Formula" if include_time else "Repair Cost Formula"

    if include_time:
        component_rows = [
            [
                "`sru`",
                config.repair_base_cost_by_class["sru"],
                config.repair_base_time_by_class["sru"],
                "Base repair cost/time for an `SRU`",
            ],
            [
                "`lru`",
                config.repair_base_cost_by_class["lru"],
                config.repair_base_time_by_class["lru"],
                "Base repair cost/time for an `LRU`",
            ],
        ]
        component_headers = ["Component Class", "Cost Value", "Time Value", "Meaning"]
        combination_rows = [
            [
                "child `part`",
                config.repair_combination_cost_by_child_class["part"],
                config.repair_combination_time_by_child_class["part"],
                "Combination cost/time per required `PART` child",
            ],
            [
                "child `sru`",
                config.repair_combination_cost_by_child_class["sru"],
                config.repair_combination_time_by_child_class["sru"],
                "Combination cost/time per required `SRU` child",
            ],
        ]
        combination_headers = ["Child Class", "Cost Value", "Time Value", "Meaning"]
        location_rows = [
            [
                "`specialized_shop`",
                config.repair_cost_multiplier_by_type["specialized_shop"],
                config.repair_time_multiplier_by_type["specialized_shop"],
            ],
            [
                "`local_shop`",
                config.repair_cost_multiplier_by_type["local_shop"],
                config.repair_time_multiplier_by_type["local_shop"],
            ],
            [
                "`regional_warehouse`",
                config.repair_cost_multiplier_by_type["regional_warehouse"],
                config.repair_time_multiplier_by_type["regional_warehouse"],
            ],
            [
                "`central_depot`",
                config.repair_cost_multiplier_by_type["central_depot"],
                config.repair_time_multiplier_by_type["central_depot"],
            ],
        ]
        location_headers = ["Location Type", "Cost Multiplier", "Time Multiplier"]
        formula_section = "## Formula\n" + "\n".join(
            [
                "```text",
                "repair_cost = round(base_repair_cost + combination_cost)",
                "repair_cost_multiplier = location_cost_multiplier",
                "repair_time = round(base_repair_time + combination_time)",
                "repair_time_multiplier = location_time_multiplier",
                "```",
                "",
                "```text",
                "base_repair_cost = repair_base_cost_by_class[component_class]",
                "base_repair_time = repair_base_time_by_class[component_class]",
                "```",
                "",
                "```text",
                "combination_cost = sum(child_combination_cost for each BOM child)",
                "combination_time = sum(child_combination_time for each BOM child)",
                "```",
                "",
                "```text",
                "if child is SRU:",
                "    child_combination_cost = 6.0 * quantity_required",
                "    child_combination_time = 7.0 * quantity_required",
                "",
                "if child is PART:",
                "    child_combination_cost = 14.0 * quantity_required",
                "    child_combination_time = 2.0 * quantity_required",
                "```",
                "",
                "Specialized shops are fastest and central depots are slowest.",
                "LRU repair takes longer than SRU repair because `LRU` assembly combines `SRU` children with a higher per-child time than `SRU` assembly uses for `PART` children.",
            ]
        )
        level_description = (
            "Only `LRU_*` and `LRU_*_*` components are repairable at `--complexity 2`. "
            "Shared `PART_*` items are used to build repairs but are not themselves repair options."
        )
    else:
        component_rows = [
            ["`sru`", config.repair_base_cost_by_class["sru"], "Base repair cost for an `SRU`"],
            ["`lru`", config.repair_base_cost_by_class["lru"], "Base repair cost for an `LRU`"],
        ]
        component_headers = ["Component Class", "Value", "Meaning"]
        combination_rows = [
            [
                "child `part`",
                config.repair_combination_cost_by_child_class["part"],
                "Combination cost per required `PART` child",
            ],
            [
                "child `sru`",
                config.repair_combination_cost_by_child_class["sru"],
                "Combination cost per required `SRU` child",
            ],
        ]
        combination_headers = ["Child Class", "Value", "Meaning"]
        location_rows = [
            ["`specialized_shop`", config.repair_cost_multiplier_by_type["specialized_shop"]],
            ["`local_shop`", config.repair_cost_multiplier_by_type["local_shop"]],
            ["`regional_warehouse`", config.repair_cost_multiplier_by_type["regional_warehouse"]],
            ["`central_depot`", config.repair_cost_multiplier_by_type["central_depot"]],
        ]
        location_headers = ["Location Type", "Multiplier"]
        formula_section = "## Formula\n" + "\n".join(
            [
                "```text",
                "repair_cost = round(base_repair_cost + combination_cost)",
                "repair_cost_multiplier = location_multiplier",
                "```",
                "",
                "```text",
                "base_repair_cost = repair_base_cost_by_class[component_class]",
                "```",
                "",
                "```text",
                "combination_cost = sum(child_combination_cost for each BOM child)",
                "```",
                "",
                "```text",
                "if child is SRU:",
                "    child_combination_cost = 6.0 * quantity_required",
                "",
                "if child is PART:",
                "    child_combination_cost = 14.0 * quantity_required",
                "```",
            ]
        )
        level_description = (
            "Only `LRU_*` and `LRU_*_*` components are repairable at `--complexity 1`. "
            "Shared `PART_*` items are used to build repairs but are not themselves repair options."
        )

    path.write_text(
        "\n\n".join(
            [
                f"# {title}",
                level_description,
                "## Component Cost Table\n"
                + markdown_table(
                    component_headers,
                    component_rows,
                ),
                "## Child Combination Cost Table\n"
                + markdown_table(
                    combination_headers,
                    combination_rows,
                ),
                "## Location Multiplier Table\n" + markdown_table(location_headers, location_rows),
                formula_section,
                "",
            ]
        )
    )


def draw_network_axis(
    axis: object,
    nodes: list[dict[str, object]],
    arcs: list[dict[str, object]],
    node_by_id: dict[str, dict[str, object]],
    config: GeneratorConfig,
) -> None:
    """Draw the supply chain network graph on an axis."""

    colors_by_type = {
        "customer": "#4c78a8",
        "local_shop": "#59a14f",
        "regional_warehouse": "#f28e2b",
        "central_depot": "#e15759",
        "specialized_shop": "#b07aa1",
    }
    markers_by_type = {
        "customer": "o",
        "local_shop": "s",
        "regional_warehouse": "^",
        "central_depot": "D",
        "specialized_shop": "P",
    }

    # Draw each bidirectional relationship once so the visualization does not
    # look like duplicate/thicker lines. The CSV still keeps both directed arcs.
    unique_relationships: dict[frozenset[str], dict[str, object]] = {}
    for arc in arcs:
        undirected_pair = frozenset((str(arc["from_node"]), str(arc["to_node"])))
        unique_relationships.setdefault(undirected_pair, arc)

    for undirected_pair in unique_relationships:
        from_node, to_node = sorted_relationship_nodes(undirected_pair, node_by_id)
        axis.plot(
            [float(from_node["x"]), float(to_node["x"])],
            [float(from_node["y"]), float(to_node["y"])],
            color="#9aa0a6",
            linewidth=0.65,
            alpha=0.28,
            zorder=1,
        )
        axis.scatter(
            [float(from_node["x"]), float(to_node["x"])],
            [float(from_node["y"]), float(to_node["y"])],
            c="#9aa0a6",
            s=12,
            alpha=0.35,
            zorder=1,
        )

    relationship_segments = {
        relationship_key: sorted_relationship_nodes(relationship_key, node_by_id)
        for relationship_key in unique_relationships
    }
    node_label_bounds = [
        node_label_avoidance_bounds(node, config)
        for node in nodes
    ]

    # Put cost labels near the midpoint of each visible relationship. The label
    # is allowed to slide along its own line if the midpoint overlaps another
    # relationship line or a node label. The opaque label box covers the line
    # segment behind it, so the line appears interrupted by the number.
    for undirected_pair, arc in unique_relationships.items():
        label_x, label_y = best_edge_label_position(
            undirected_pair,
            relationship_segments,
            node_label_bounds,
        )
        axis.annotate(
            str(arc["cost"]),
            (label_x, label_y),
            fontsize=8,
            fontweight="bold",
            color="#222222",
            ha="center",
            va="center",
            bbox={
                "boxstyle": "square,pad=0.18",
                "facecolor": "white",
                "edgecolor": "white",
                "linewidth": 0.0,
                "alpha": 1.0,
            },
            zorder=4,
        )

    for node_type in NODE_TYPES:
        typed_nodes = [node for node in nodes if node["node_type"] == node_type]
        if not typed_nodes:
            continue

        axis.scatter(
            [float(node["x"]) for node in typed_nodes],
            [float(node["y"]) for node in typed_nodes],
            label=node_type,
            c=colors_by_type[node_type],
            marker=markers_by_type[node_type],
            edgecolors="black",
            linewidths=0.6,
            s=85,
            zorder=2,
        )

    for node in nodes:
        label = str(node["node_id"])
        if "repair_capability" in node and node["node_type"] != "customer":
            label = f"{label}\nskill={node['repair_capability']}"

        offset_x, offset_y, horizontal_alignment, vertical_alignment = simple_node_label_offset(
            node, config
        )
        axis.annotate(
            label,
            (float(node["x"]), float(node["y"])),
            xytext=(offset_x, offset_y),
            textcoords="offset points",
            fontsize=7,
            ha=horizontal_alignment,
            va=vertical_alignment,
            bbox={
                "boxstyle": "round,pad=0.18",
                "facecolor": "white",
                "edgecolor": "#777777",
                "linewidth": 0.4,
                "alpha": 0.95,
            },
            zorder=5,
        )

    axis.set_title("Generated Reverse Supply Chain Network")
    axis.set_xlabel("x coordinate")
    axis.set_ylabel("y coordinate")
    axis.set_xlim(config.coordinate_min - 3, config.coordinate_max + 3)
    axis.set_ylim(config.coordinate_min - 3, config.coordinate_max + 3)
    axis.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
    axis.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), borderaxespad=0.0)
    axis.set_aspect("equal", adjustable="box")


def prepare_matplotlib(output_path: Path):
    """Import matplotlib and configure local cache directories."""

    cache_dir = output_path.parent / ".plot_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_dir))

    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise SystemExit(
            "The --visualize option requires matplotlib. Install it with "
            "`python3 -m pip install matplotlib` and rerun the command."
        ) from exc
    return plt


def write_visualization(
    output_path: Path,
    nodes: list[dict[str, object]],
    arcs: list[dict[str, object]],
    inventory: list[dict[str, object]],
    demand: list[dict[str, object]],
    components: list[dict[str, object]],
    bom_rows: list[dict[str, object]],
    config: GeneratorConfig,
) -> None:
    """Write a combined labeled network, inventory, and BOM plot."""

    plt = prepare_matplotlib(output_path)
    node_by_id, inventory_by_node, demand_by_node = visualization_maps(
        nodes, inventory, demand
    )

    figure = plt.figure(figsize=(22, 8), constrained_layout=True)
    grid = figure.add_gridspec(
        1,
        3,
        width_ratios=[1.45, 2.10, 1.45],
        wspace=0.04,
    )
    table_grid = grid[0, 0].subgridspec(
        2,
        1,
        height_ratios=[2.7, 0.75],
        hspace=0.05,
    )
    inventory_axis = figure.add_subplot(table_grid[0, 0])
    demand_axis = figure.add_subplot(table_grid[1, 0])
    graph_axis = figure.add_subplot(grid[0, 1])
    bom_axis = figure.add_subplot(grid[0, 2])

    draw_inventory_axes(
        inventory_axis, demand_axis, nodes, inventory_by_node, demand_by_node
    )
    draw_network_axis(graph_axis, nodes, arcs, node_by_id, config)
    draw_bom_axis(bom_axis, components, bom_rows)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=200)
    plt.close(figure)

    cost_formula_path = output_path.with_name(f"{output_path.stem}_cost_formula.md")
    write_cost_formula_markdown(cost_formula_path, config)


def write_separate_visualizations(
    output_path: Path,
    nodes: list[dict[str, object]],
    arcs: list[dict[str, object]],
    inventory: list[dict[str, object]],
    demand: list[dict[str, object]],
    components: list[dict[str, object]],
    bom_rows: list[dict[str, object]],
    config: GeneratorConfig,
) -> list[Path]:
    """Write graph PNG plus dependency-map, inventory, and cost Markdown files."""

    plt = prepare_matplotlib(output_path)
    node_by_id, inventory_by_node, demand_by_node = visualization_maps(
        nodes, inventory, demand
    )
    stem = output_path.stem
    suffix = output_path.suffix or ".png"
    graph_path = output_path.with_name(f"{stem}_graph{suffix}")
    dependency_map_path = output_path.with_name(f"{stem}_dependency_map.md")
    inventory_path = output_path.with_name(f"{stem}_inventory.md")
    cost_formula_path = output_path.with_name(f"{stem}_cost_formula.md")
    written_paths = [
        graph_path,
        dependency_map_path,
        inventory_path,
        cost_formula_path,
    ]

    graph_figure, graph_axis = plt.subplots(figsize=(10, 8), constrained_layout=True)
    draw_network_axis(graph_axis, nodes, arcs, node_by_id, config)
    graph_figure.savefig(graph_path, dpi=200)
    plt.close(graph_figure)

    write_dependency_map_markdown(dependency_map_path, components, bom_rows)
    write_inventory_markdown(
        inventory_path,
        nodes,
        inventory_by_node,
        demand_by_node,
    )
    write_cost_formula_markdown(cost_formula_path, config)

    return written_paths


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    """Write rows to CSV, creating the output directory if needed."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def node_fieldnames(config: GeneratorConfig) -> list[str]:
    """Return the nodes.csv schema for the selected complexity level."""

    fieldnames = ["node_id", "node_type", "x", "y"]
    if config.complexity >= 1:
        fieldnames.extend(["repair_capability", "repair_capacity"])
    return fieldnames


def repair_option_fieldnames(config: GeneratorConfig) -> list[str]:
    """Return the component_multipler.csv schema for the selected complexity level."""

    fieldnames = ["node_id", "component_id"]
    if config.complexity >= 1:
        fieldnames.append("repair_cost_multiplier")
    if config.complexity >= 2:
        fieldnames.append("repair_time")
        fieldnames.append("repair_time_multiplier")
    return fieldnames


def summarize(
    nodes: list[dict[str, object]],
    inventory: list[dict[str, object]],
    demand: list[dict[str, object]],
    arcs: list[dict[str, object]],
    repair_options: list[dict[str, object]],
    bom_rows: list[dict[str, object]],
) -> list[str]:
    """Build a small command-line summary for quick sanity checks."""

    node_counts = {node_type: 0 for node_type in NODE_TYPES}
    for node in nodes:
        node_counts[str(node["node_type"])] += 1

    node_type_by_id = {str(node["node_id"]): str(node["node_type"]) for node in nodes}
    inventory_totals = {node_type: 0 for node_type in NODE_TYPES}
    for row in inventory:
        node_type = node_type_by_id[str(row["node_id"])]
        inventory_totals[node_type] += int(row["quantity"])

    demand_totals = {node_type: 0 for node_type in NODE_TYPES}
    for row in demand:
        node_type = node_type_by_id[str(row["node_id"])]
        demand_totals[node_type] += int(row["quantity"])

    lines = ["Generated node counts:"]
    lines.extend(f"  {node_type}: {count}" for node_type, count in node_counts.items())
    lines.append("Generated total inventory by node type:")
    lines.extend(f"  {node_type}: {quantity}" for node_type, quantity in inventory_totals.items())
    lines.append("Generated total demand by node type:")
    lines.extend(f"  {node_type}: {quantity}" for node_type, quantity in demand_totals.items())
    lines.append(f"Generated arcs: {len(arcs)}")
    if repair_options:
        lines.append(f"Generated repair options: {len(repair_options)}")
    lines.append(f"Generated BOM relationships: {len(bom_rows)}")
    return lines


def main() -> None:
    args = parse_args()

    # Command-line flags only override the high-level counts and seed for now.
    # More detailed behavior can be tuned by editing GeneratorConfig defaults.
    config = GeneratorConfig(
        complexity=args.complexity,
        seed=args.seed,
        counts=CountConfig(
            customers=args.customers,
            local_shops=args.local_shops,
            regional_warehouses=args.regional_warehouses,
            central_depots=args.central_depots,
            specialized_shops=args.specialized_shops,
            **component_count_config_from_total(args.components),
        ),
    )
    rng = random.Random(config.seed)
    output_dir = Path(args.output_dir)
    obsolete_filenames = ["customers.csv", "repair_options.csv"]
    if config.complexity == 0:
        obsolete_filenames.extend(["components.csv", "component_multipler.csv"])
    for obsolete_filename in obsolete_filenames:
        obsolete_path = output_dir / obsolete_filename
        if obsolete_path.exists():
            obsolete_path.unlink()

    # Generation order matters: inventory and demand both use node attributes
    # and component attributes.
    nodes = generate_nodes(config, rng)
    components, bom_rows = generate_components_and_bom(config, rng)
    if config.complexity == 0:
        components = components_used_by_bom(components, bom_rows)
    inventory = generate_inventory(nodes, components, config, rng)
    demand = generate_demand(nodes, components, config, rng)
    if config.complexity == 0:
        ensure_demand_can_be_met_through_bom(
            inventory,
            nodes,
            components,
            bom_rows,
            demand,
            config,
            rng,
        )
    arcs = generate_arcs(nodes, config)
    repair_options = (
        generate_repair_options(nodes, components, bom_rows, config)
        if config.complexity >= 1
        else []
    )

    # Keep inventory and demand in separate normalized tables instead of
    # embedding lists inside nodes.csv. This will be easier to load into an
    # optimization model.
    write_csv(
        output_dir / "nodes.csv",
        nodes,
        node_fieldnames(config),
    )
    if config.complexity >= 1:
        component_fieldnames = [
            "component_id",
            "component_class",
            "subsystem",
            "repair_difficulty",
            "component_cost",
        ]
        if config.complexity >= 3:
            component_fieldnames.append("movement_cost")
        component_fieldnames.extend(
            [
                "indenture_level",
                "is_shared",
                "specialized_only",
            ]
        )
        write_csv(
            output_dir / "components.csv",
            components,
            component_fieldnames,
        )
    bom_fieldnames = [
        "parent_component_id",
        "parent_component_class",
        "parent_component_cost",
        "child_component_id",
        "child_component_class",
        "child_component_cost",
    ]
    if config.complexity >= 3:
        bom_fieldnames.extend(
            [
                "parent_component_movement_cost",
                "child_component_movement_cost",
            ]
        )
    bom_fieldnames.extend(
        [
            "child_specialized_only",
            "quantity_required",
        ]
    )
    write_csv(
        output_dir / "bom.csv",
        enriched_bom_rows(components, bom_rows, config),
        bom_fieldnames,
    )
    write_csv(
        output_dir / "node_inventory.csv",
        inventory,
        ["node_id", "component_id", "quantity"],
    )
    write_csv(
        output_dir / "demand.csv",
        demand,
        ["demand_id", "node_id", "component_id", "quantity"],
    )
    write_csv(
        output_dir / "arcs.csv",
        arcs,
        ["arc_id", "from_node", "to_node", "cost"],
    )
    if config.complexity >= 1:
        write_csv(
            output_dir / "component_multipler.csv",
            repair_options,
            repair_option_fieldnames(config),
        )

    if args.visualize:
        visualization_path = output_dir / args.visualization_file
        if args.visualization_layout == "separate":
            visualization_paths = write_separate_visualizations(
                visualization_path,
                nodes,
                arcs,
                inventory,
                demand,
                components,
                bom_rows,
                config,
            )
            for path in visualization_paths:
                print(f"Wrote visualization to {path}")
        else:
            write_visualization(
                visualization_path,
                nodes,
                arcs,
                inventory,
                demand,
                components,
                bom_rows,
                config,
            )
            print(f"Wrote visualization to {visualization_path}")

    print(f"Wrote data to {output_dir}")
    print("Arc cost is straight-line Euclidean distance between node coordinates.")
    for line in summarize(nodes, inventory, demand, arcs, repair_options, bom_rows):
        print(line)


if __name__ == "__main__":
    main()
