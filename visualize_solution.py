#!/usr/bin/env python3
"""Visualize solved reverse supply chain flows and repairs on a generated network."""

from __future__ import annotations

import argparse
import csv
import math
import os
from collections import Counter, defaultdict
from pathlib import Path


NODE_TYPES = (
    "customer",
    "local_shop",
    "regional_warehouse",
    "central_depot",
    "specialized_shop",
)

COLORS_BY_TYPE = {
    "customer": "#4c78a8",
    "local_shop": "#59a14f",
    "regional_warehouse": "#f28e2b",
    "central_depot": "#e15759",
    "specialized_shop": "#b07aa1",
}

MARKERS_BY_TYPE = {
    "customer": "o",
    "local_shop": "s",
    "regional_warehouse": "^",
    "central_depot": "D",
    "specialized_shop": "P",
}

COMPONENT_PALETTE = (
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize solver flow_output.csv and repair_output.csv on top of generated network data."
    )
    parser.add_argument("--data-dir", required=True, help="Directory like level0data")
    parser.add_argument("--output-dir", required=True, help="Directory like level0output")
    parser.add_argument(
        "--image-file",
        default="solution_network_all.png",
        help="Filename for the aggregate PNG inside output-dir",
    )
    parser.add_argument(
        "--summary-file",
        default="solution_summary.md",
        help="Filename for the Markdown summary inside output-dir",
    )
    parser.add_argument(
        "--component",
        action="append",
        default=[],
        help="Limit rendering to one or more component ids",
    )
    parser.add_argument(
        "--per-component",
        action="store_true",
        help="Also render one PNG per component with any flow or repair activity",
    )
    parser.add_argument(
        "--per-timestep",
        action="store_true",
        help="Also render one aggregate PNG per timestep using flow/repair rows from that slice only",
    )
    parser.add_argument(
        "--family-root",
        action="append",
        default=[],
        help="Render one or more BOM families rooted at these component ids",
    )
    return parser.parse_args()


def prepare_matplotlib(output_path: Path):
    """Import matplotlib and configure local cache directories."""

    cache_dir = output_path.parent / ".plot_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_dir))

    try:
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyArrowPatch
    except ImportError as exc:
        raise SystemExit(
            "This script requires matplotlib. Install it with "
            "`python3 -m pip install matplotlib` and rerun."
        ) from exc
    return plt, FancyArrowPatch


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def load_inputs(
    data_dir: Path, output_dir: Path
) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    nodes = read_csv(data_dir / "nodes.csv")
    arcs = read_csv(data_dir / "arcs.csv")
    demand = read_csv(data_dir / "demand.csv")
    bom_rows = read_csv(data_dir / "bom.csv")
    flow_rows = read_csv(output_dir / "flow_output.csv")
    repair_rows = read_csv(output_dir / "repair_output.csv")
    return nodes, arcs, demand, bom_rows, flow_rows, repair_rows


def node_lookup(nodes: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row["node_id"]: row for row in nodes}


def unique_relationships(
    arcs: list[dict[str, str]],
) -> dict[frozenset[str], dict[str, str]]:
    relationships: dict[frozenset[str], dict[str, str]] = {}
    for arc in arcs:
        key = frozenset((arc["from_node"], arc["to_node"]))
        relationships.setdefault(key, arc)
    return relationships


def demand_totals_by_node(demand_rows: list[dict[str, str]]) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for row in demand_rows:
        totals[row["node_id"]] += int(row["quantity"])
    return dict(totals)


def active_components(
    flow_rows: list[dict[str, str]], repair_rows: list[dict[str, str]]
) -> list[str]:
    component_ids = {row["comp_id"] for row in flow_rows}
    component_ids.update(row["comp_id"] for row in repair_rows)
    return sorted(component_ids)


def active_timesteps(
    flow_rows: list[dict[str, str]], repair_rows: list[dict[str, str]]
) -> list[str]:
    timestep_values = {row["timestep"] for row in flow_rows if row.get("timestep")}
    timestep_values.update(row["timestep"] for row in repair_rows if row.get("timestep"))
    return sorted(timestep_values, key=lambda value: int(value))


def filter_rows_by_timestep(
    rows: list[dict[str, str]], timestep: str | None
) -> list[dict[str, str]]:
    if timestep is None:
        return rows
    return [row for row in rows if row.get("timestep") == timestep]


def bom_children_by_parent(bom_rows: list[dict[str, str]]) -> dict[str, list[str]]:
    children_by_parent: dict[str, list[str]] = defaultdict(list)
    for row in bom_rows:
        children_by_parent[row["parent_component_id"]].append(row["child_component_id"])
    return dict(children_by_parent)


def family_components(root_component_id: str, bom_rows: list[dict[str, str]]) -> list[str]:
    children_by_parent = bom_children_by_parent(bom_rows)
    ordered_components: list[str] = []
    visited: set[str] = set()
    stack = [root_component_id]

    while stack:
        component_id = stack.pop()
        if component_id in visited:
            continue
        visited.add(component_id)
        ordered_components.append(component_id)
        stack.extend(reversed(children_by_parent.get(component_id, [])))

    return ordered_components


def family_tree_lines(root_component_id: str, bom_rows: list[dict[str, str]]) -> list[str]:
    children_by_parent = bom_children_by_parent(bom_rows)
    lines = [root_component_id]

    def visit(component_id: str, prefix: str) -> None:
        children = children_by_parent.get(component_id, [])
        for index, child_id in enumerate(children):
            connector = "`-- " if index == len(children) - 1 else "|-- "
            lines.append(f"{prefix}{connector}{child_id}")
            next_prefix = f"{prefix}{'    ' if index == len(children) - 1 else '|   '}"
            visit(child_id, next_prefix)

    visit(root_component_id, "")
    return lines


def component_styles(component_ids: list[str]) -> dict[str, dict[str, str]]:
    styles: dict[str, dict[str, str]] = {}
    for index, component_id in enumerate(component_ids):
        styles[component_id] = {
            "color": COMPONENT_PALETTE[index % len(COMPONENT_PALETTE)],
        }
    return styles


def aggregate_solution(
    flow_rows: list[dict[str, str]],
    repair_rows: list[dict[str, str]],
    component_filter: set[str] | None,
) -> tuple[dict[tuple[str, str], int], dict[str, int], list[dict[str, str]], list[dict[str, str]]]:
    filtered_flows = [
        row for row in flow_rows if not component_filter or row["comp_id"] in component_filter
    ]
    filtered_repairs = [
        row for row in repair_rows if not component_filter or row["comp_id"] in component_filter
    ]

    flow_totals: dict[tuple[str, str], int] = defaultdict(int)
    for row in filtered_flows:
        flow_totals[(row["node_from"], row["node_to"])] += int(row["qty"])

    repair_totals: dict[str, int] = defaultdict(int)
    for row in filtered_repairs:
        repair_totals[row["node_id"]] += int(row["qty"])

    return dict(flow_totals), dict(repair_totals), filtered_flows, filtered_repairs


def validate_solution(
    flow_rows: list[dict[str, str]],
    repair_rows: list[dict[str, str]],
    nodes: list[dict[str, str]],
    arcs: list[dict[str, str]],
) -> list[str]:
    node_ids = {row["node_id"] for row in nodes}
    arc_pairs = {(row["from_node"], row["to_node"]) for row in arcs}
    issues: list[str] = []

    for row in flow_rows:
        pair = (row["node_from"], row["node_to"])
        if pair not in arc_pairs:
            issues.append(
                f"Flow arc missing from data network: {row['comp_id']} {row['node_from']} -> {row['node_to']}"
            )

    for row in repair_rows:
        if row["node_id"] not in node_ids:
            issues.append(f"Repair node missing from data network: {row['comp_id']} at {row['node_id']}")

    return issues


def offset_point(x1: float, y1: float, x2: float, y2: float, magnitude: float) -> tuple[float, float]:
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length == 0:
        return 0.0, 0.0
    return (-dy / length) * magnitude, (dx / length) * magnitude


def along_line_point(x1: float, y1: float, x2: float, y2: float, magnitude: float) -> tuple[float, float]:
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length == 0:
        return 0.0, 0.0
    return (dx / length) * magnitude, (dy / length) * magnitude


def draw_component_legend(
    axis: object,
    component_ids: list[str],
    styles: dict[str, dict[str, str]],
    family_lines: list[str] | None,
) -> None:
    box_x = 1.01
    box_top_y = 0.76
    line_height = 0.032
    family_extra_lines = 0 if not family_lines else len(family_lines) + 2
    box_height = line_height * (len(component_ids) + family_extra_lines + 1.6)

    axis.text(
        box_x,
        box_top_y,
        "",
        transform=axis.transAxes,
        fontsize=8,
        family="monospace",
        va="top",
        ha="left",
        bbox={
            "boxstyle": "round,pad=0.30",
            "facecolor": "white",
            "edgecolor": "#999999",
            "linewidth": 0.5,
            "alpha": 0.96,
        },
    )

    axis.text(
        box_x + 0.01,
        box_top_y - 0.01,
        "component colors:",
        transform=axis.transAxes,
        fontsize=8,
        family="monospace",
        va="top",
        ha="left",
        color="#222222",
    )

    current_y = box_top_y - line_height
    for component_id in component_ids:
        axis.text(
            box_x + 0.01,
            current_y,
            f"\u25a0 {component_id}",
            transform=axis.transAxes,
            fontsize=8,
            family="monospace",
            va="top",
            ha="left",
            color=styles[component_id]["color"],
        )
        current_y -= line_height

    if family_lines:
        current_y -= line_height * 0.35
        axis.text(
            box_x + 0.01,
            current_y,
            "BOM family:",
            transform=axis.transAxes,
            fontsize=8,
            family="monospace",
            va="top",
            ha="left",
            color="#222222",
        )
        current_y -= line_height
        for family_line in family_lines:
            axis.text(
                box_x + 0.01,
                current_y,
                family_line,
                transform=axis.transAxes,
                fontsize=8,
                family="monospace",
                va="top",
                ha="left",
                color="#222222",
            )
            current_y -= line_height


def draw_solution(
    output_path: Path,
    title: str,
    nodes: list[dict[str, str]],
    arcs: list[dict[str, str]],
    demand_rows: list[dict[str, str]],
    flow_totals: dict[tuple[str, str], int],
    repair_totals: dict[str, int],
    flow_rows: list[dict[str, str]],
    repair_rows: list[dict[str, str]],
    component_label: str | None = None,
    component_styles_by_id: dict[str, dict[str, str]] | None = None,
    family_lines: list[str] | None = None,
    timestep_label: str | None = None,
    timestep_scope: list[str] | None = None,
) -> None:
    plt, FancyArrowPatch = prepare_matplotlib(output_path)
    node_by_id = node_lookup(nodes)
    demand_by_node = demand_totals_by_node(demand_rows)

    figure, axis = plt.subplots(figsize=(12, 9), constrained_layout=True)

    for relationship_key in unique_relationships(arcs):
        node_a_id, node_b_id = sorted(relationship_key)
        node_a = node_by_id[node_a_id]
        node_b = node_by_id[node_b_id]
        axis.plot(
            [float(node_a["x"]), float(node_b["x"])],
            [float(node_a["y"]), float(node_b["y"])],
            color="#c6cbd2",
            linewidth=1.0,
            alpha=0.55,
            zorder=1,
        )

    if component_styles_by_id:
        component_flow_max: dict[str, int] = defaultdict(int)
        for row in flow_rows:
            component_flow_max[row["comp_id"]] = max(
                component_flow_max[row["comp_id"]],
                int(row["qty"]),
            )

        for component_id in sorted(component_styles_by_id):
            component_rows = [row for row in flow_rows if row["comp_id"] == component_id]
            for row in component_rows:
                from_node_id = row["node_from"]
                to_node_id = row["node_to"]
                quantity = int(row["qty"])
                from_node = node_by_id[from_node_id]
                to_node = node_by_id[to_node_id]
                x1 = float(from_node["x"])
                y1 = float(from_node["y"])
                x2 = float(to_node["x"])
                y2 = float(to_node["y"])
                width = (
                    1.5
                    if component_flow_max[component_id] <= 0
                    else 1.0 + 4.0 * (quantity / component_flow_max[component_id])
                )
                style_index = list(sorted(component_styles_by_id)).index(component_id)
                offset_magnitude = 0.8 + 0.9 * style_index
                offset_x, offset_y = offset_point(x1, y1, x2, y2, offset_magnitude)
                along_x, along_y = along_line_point(
                    x1,
                    y1,
                    x2,
                    y2,
                    -1.0 + 1.1 * style_index,
                )
                label_x = (x1 + x2) / 2.0 + offset_x + along_x
                label_y = (y1 + y2) / 2.0 + offset_y + along_y
                color = component_styles_by_id[component_id]["color"]
                arrow = FancyArrowPatch(
                    (x1 + offset_x, y1 + offset_y),
                    (x2 + offset_x, y2 + offset_y),
                    arrowstyle="-|>",
                    mutation_scale=10 + width * 2.0,
                    linewidth=width,
                    color=color,
                    alpha=0.82,
                    shrinkA=9,
                    shrinkB=9,
                    zorder=3,
                )
                axis.add_patch(arrow)
                axis.text(
                    label_x,
                    label_y,
                    f"{component_id}:{quantity}",
                    fontsize=7,
                    fontweight="bold",
                    color=color,
                    ha="center",
                    va="center",
                    bbox={
                        "boxstyle": "round,pad=0.16",
                        "facecolor": "white",
                        "edgecolor": color,
                        "linewidth": 0.4,
                        "alpha": 0.95,
                    },
                    zorder=4,
                )
    else:
        max_flow = max(flow_totals.values(), default=0)
        for (from_node_id, to_node_id), quantity in sorted(flow_totals.items()):
            from_node = node_by_id[from_node_id]
            to_node = node_by_id[to_node_id]
            x1 = float(from_node["x"])
            y1 = float(from_node["y"])
            x2 = float(to_node["x"])
            y2 = float(to_node["y"])
            width = 1.5 if max_flow <= 0 else 1.0 + 4.0 * (quantity / max_flow)
            offset_x, offset_y = offset_point(x1, y1, x2, y2, 0.9)
            arrow = FancyArrowPatch(
                (x1 + offset_x, y1 + offset_y),
                (x2 + offset_x, y2 + offset_y),
                arrowstyle="-|>",
                mutation_scale=10 + width * 2.2,
                linewidth=width,
                color="#2f6db0",
                alpha=0.78,
                shrinkA=9,
                shrinkB=9,
                zorder=3,
            )
            axis.add_patch(arrow)
            axis.text(
                (x1 + x2) / 2.0 + offset_x,
                (y1 + y2) / 2.0 + offset_y,
                str(quantity),
                fontsize=8,
                fontweight="bold",
                color="#1f3552",
                ha="center",
                va="center",
                bbox={
                    "boxstyle": "round,pad=0.18",
                    "facecolor": "white",
                    "edgecolor": "#9fb6d0",
                    "linewidth": 0.4,
                    "alpha": 0.95,
                },
                zorder=4,
            )

    max_repair = max(repair_totals.values(), default=0)
    for node_type in NODE_TYPES:
        typed_nodes = [node for node in nodes if node["node_type"] == node_type]
        if not typed_nodes:
            continue

        axis.scatter(
            [float(node["x"]) for node in typed_nodes],
            [float(node["y"]) for node in typed_nodes],
            label=node_type,
            c=COLORS_BY_TYPE[node_type],
            marker=MARKERS_BY_TYPE[node_type],
            edgecolors="black",
            linewidths=0.6,
            s=90,
            zorder=5,
        )

    if component_styles_by_id:
        component_repair_max: dict[str, int] = defaultdict(int)
        for row in repair_rows:
            component_repair_max[row["comp_id"]] = max(
                component_repair_max[row["comp_id"]],
                int(row["qty"]),
            )
        repair_rings_by_node: dict[str, list[tuple[float, str]]] = defaultdict(list)
        for component_id in sorted(component_styles_by_id):
            component_rows = [row for row in repair_rows if row["comp_id"] == component_id]
            for row in component_rows:
                quantity = int(row["qty"])
                base_size = (
                    220
                    if component_repair_max[component_id] <= 0
                    else 160 + 900 * (quantity / component_repair_max[component_id])
                )
                repair_rings_by_node[row["node_id"]].append(
                    (base_size, component_styles_by_id[component_id]["color"])
                )

        ring_step = 210
        for node_id, ring_specs in sorted(repair_rings_by_node.items()):
            node = node_by_id[node_id]
            sorted_ring_specs = sorted(ring_specs, reverse=True)
            for ring_index, (base_size, color) in enumerate(sorted_ring_specs):
                size = base_size + (len(sorted_ring_specs) - ring_index - 1) * ring_step
                axis.scatter(
                    [float(node["x"])],
                    [float(node["y"])],
                    s=size,
                    facecolors="none",
                    edgecolors=color,
                    linewidths=2.4,
                    zorder=6,
                )
    else:
        for node_id, quantity in sorted(repair_totals.items()):
            node = node_by_id[node_id]
            size = 220 if max_repair <= 0 else 160 + 900 * (quantity / max_repair)
            axis.scatter(
                [float(node["x"])],
                [float(node["y"])],
                s=size,
                facecolors="none",
                edgecolors="#d62728",
                linewidths=2.0,
                zorder=6,
            )

    for node in nodes:
        node_id = node["node_id"]
        details = [node_id]
        repair_quantity = repair_totals.get(node_id, 0)
        if repair_quantity:
            details.append(f"repair={repair_quantity}")

        axis.annotate(
            "\n".join(details),
            (float(node["x"]), float(node["y"])),
            xytext=(6, 6),
            textcoords="offset points",
            fontsize=7,
            ha="left",
            va="bottom",
            bbox={
                "boxstyle": "round,pad=0.18",
                "facecolor": "white",
                "edgecolor": "#777777",
                "linewidth": 0.4,
                "alpha": 0.95,
            },
            zorder=7,
        )

    if component_styles_by_id:
        active_component_ids = sorted(
            {
                row["comp_id"]
                for row in flow_rows + repair_rows
                if row["comp_id"] in component_styles_by_id
            }
        )
        draw_component_legend(
            axis,
            active_component_ids,
            component_styles_by_id,
            family_lines,
        )
    else:
        total_flow_qty = sum(int(row["qty"]) for row in flow_rows)
        total_repair_qty = sum(int(row["qty"]) for row in repair_rows)
        component_counter = Counter(row["comp_id"] for row in flow_rows)
        summary_lines = [
            f"flow rows: {len(flow_rows)}",
            f"repair rows: {len(repair_rows)}",
            f"total shipped qty: {total_flow_qty}",
            f"total repaired qty: {total_repair_qty}",
        ]
        if timestep_label is not None:
            summary_lines.insert(0, f"timestep: {timestep_label}")
        elif timestep_scope:
            summary_lines.insert(0, f"timesteps: {', '.join(timestep_scope)}")
        if component_label is not None:
            summary_lines.insert(0, f"component: {component_label}")
        elif component_counter:
            summary_lines.append(f"active components: {len(component_counter)}")

        axis.text(
            1.01,
            0.30,
            "\n".join(summary_lines),
            transform=axis.transAxes,
            fontsize=8,
            va="top",
            ha="left",
            bbox={
                "boxstyle": "round,pad=0.30",
                "facecolor": "white",
                "edgecolor": "#999999",
                "linewidth": 0.5,
                "alpha": 0.96,
            },
        )

    axis.set_title(title)
    axis.set_xlabel("x coordinate")
    axis.set_ylabel("y coordinate")
    axis.set_xlim(-3, 103)
    axis.set_ylim(-3, 103)
    axis.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
    axis.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), borderaxespad=0.0)
    axis.set_aspect("equal", adjustable="box")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=200)
    plt.close(figure)


def write_summary(
    path: Path,
    data_dir: Path,
    output_dir: Path,
    demand_rows: list[dict[str, str]],
    flow_rows: list[dict[str, str]],
    repair_rows: list[dict[str, str]],
    issues: list[str],
    timestep_scope: list[str] | None = None,
) -> None:
    demand_by_node = demand_totals_by_node(demand_rows)
    flow_by_component: dict[str, int] = defaultdict(int)
    repair_by_component: dict[str, int] = defaultdict(int)
    for row in flow_rows:
        flow_by_component[row["comp_id"]] += int(row["qty"])
    for row in repair_rows:
        repair_by_component[row["comp_id"]] += int(row["qty"])

    component_ids = sorted(set(flow_by_component) | set(repair_by_component))
    lines = [
        "# Solution Summary",
        "",
        f"- data dir: `{data_dir}`",
        f"- output dir: `{output_dir}`",
        f"- total demand qty: `{sum(demand_by_node.values())}`",
        f"- total shipped qty: `{sum(flow_by_component.values())}`",
        f"- total repaired qty: `{sum(repair_by_component.values())}`",
        f"- active components: `{len(component_ids)}`",
    ]
    if timestep_scope:
        lines.append(f"- timesteps: `{', '.join(timestep_scope)}`")

    lines.extend(
        [
            "",
            "## Component Totals",
            "",
            "| component | shipped_qty | repaired_qty |",
            "| --- | ---: | ---: |",
        ]
    )
    for component_id in component_ids:
        lines.append(
            f"| {component_id} | {flow_by_component.get(component_id, 0)} | {repair_by_component.get(component_id, 0)} |"
        )

    if timestep_scope:
        lines.extend(
            [
                "",
                "## Timestep Totals",
                "",
                "| timestep | shipped_qty | repaired_qty |",
                "| --- | ---: | ---: |",
            ]
        )
        for timestep in timestep_scope:
            timestep_flows = filter_rows_by_timestep(flow_rows, timestep)
            timestep_repairs = filter_rows_by_timestep(repair_rows, timestep)
            lines.append(
                f"| {timestep} | {sum(int(row['qty']) for row in timestep_flows)} | {sum(int(row['qty']) for row in timestep_repairs)} |"
            )

    lines.extend(
        [
            "",
            "## Demand By Customer",
            "",
            "| node | demand_qty |",
            "| --- | ---: |",
        ]
    )
    for node_id, quantity in sorted(demand_by_node.items()):
        lines.append(f"| {node_id} | {quantity} |")

    lines.extend(["", "## Validation", ""])
    if issues:
        lines.extend(f"- {issue}" for issue in issues)
    else:
        lines.append("- All flow arcs and repair nodes matched the paired data files.")

    path.write_text("\n".join(lines) + "\n")


def component_slug(component_id: str) -> str:
    return component_id.lower().replace("/", "_")


def timestep_slug(timestep: str) -> str:
    return f"t{timestep}"


def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)

    nodes, arcs, demand_rows, bom_rows, flow_rows, repair_rows = load_inputs(data_dir, output_dir)
    issues = validate_solution(flow_rows, repair_rows, nodes, arcs)
    timestep_scope = active_timesteps(flow_rows, repair_rows)

    family_roots = list(dict.fromkeys(args.family_root))
    if family_roots:
        family_components_flat: list[str] = []
        family_line_blocks: list[str] = []
        for family_root in family_roots:
            family_members = family_components(family_root, bom_rows)
            family_components_flat.extend(family_members)
            family_line_blocks.extend(family_tree_lines(family_root, bom_rows))
            family_line_blocks.append("")
        if family_line_blocks and family_line_blocks[-1] == "":
            family_line_blocks.pop()
        family_components_flat = list(dict.fromkeys(family_components_flat))
        family_filter = set(family_components_flat)
        family_styles = component_styles(family_components_flat)
        family_flow_totals, family_repair_totals, family_flows, family_repairs = aggregate_solution(
            flow_rows, repair_rows, family_filter
        )
        draw_solution(
            output_dir / args.image_file,
            f"Solution Overlay Family: {', '.join(family_roots)}",
            nodes,
            arcs,
            demand_rows,
            family_flow_totals,
            family_repair_totals,
            family_flows,
            family_repairs,
            ", ".join(family_roots),
            component_styles_by_id=family_styles,
            family_lines=family_line_blocks,
            timestep_scope=timestep_scope,
        )
        write_summary(
            output_dir / args.summary_file,
            data_dir,
            output_dir,
            demand_rows,
            family_flows,
            family_repairs,
            issues,
            timestep_scope=timestep_scope,
        )
        return

    selected_components = set(args.component)
    aggregate_filter = selected_components if selected_components else None
    flow_totals, repair_totals, filtered_flows, filtered_repairs = aggregate_solution(
        flow_rows, repair_rows, aggregate_filter
    )

    title = f"Solution Overlay: {data_dir.name} + {output_dir.name}"
    if selected_components:
        title = f"{title} ({', '.join(sorted(selected_components))})"
    if timestep_scope:
        title = f"{title} [timesteps: {', '.join(timestep_scope)}]"

    draw_solution(
        output_dir / args.image_file,
        title,
        nodes,
        arcs,
        demand_rows,
        flow_totals,
        repair_totals,
        filtered_flows,
        filtered_repairs,
        ", ".join(sorted(selected_components)) if selected_components else None,
        timestep_scope=timestep_scope,
    )

    write_summary(
        output_dir / args.summary_file,
        data_dir,
        output_dir,
        demand_rows,
        filtered_flows,
        filtered_repairs,
        issues,
        timestep_scope=timestep_scope,
    )

    if args.per_timestep:
        timestep_dir = output_dir / "solution_by_timestep"
        image_path = Path(args.image_file)
        for timestep in timestep_scope:
            timestep_flows = filter_rows_by_timestep(filtered_flows, timestep)
            timestep_repairs = filter_rows_by_timestep(filtered_repairs, timestep)
            if not timestep_flows and not timestep_repairs:
                continue

            timestep_flow_totals, timestep_repair_totals, _, _ = aggregate_solution(
                timestep_flows, timestep_repairs, None
            )
            timestep_title = f"Solution Overlay: {data_dir.name} + {output_dir.name} [timestep {timestep}]"
            if selected_components:
                timestep_title = (
                    f"{timestep_title} ({', '.join(sorted(selected_components))})"
                )
            draw_solution(
                timestep_dir / f"{image_path.stem}_{timestep_slug(timestep)}{image_path.suffix or '.png'}",
                timestep_title,
                nodes,
                arcs,
                demand_rows,
                timestep_flow_totals,
                timestep_repair_totals,
                timestep_flows,
                timestep_repairs,
                ", ".join(sorted(selected_components)) if selected_components else None,
                timestep_label=timestep,
            )

    if args.per_component:
        component_dir = output_dir / "solution_by_component"
        component_ids = sorted(selected_components) if selected_components else active_components(
            flow_rows, repair_rows
        )
        for component_id in component_ids:
            component_filter = {component_id}
            component_flow_totals, component_repair_totals, component_flows, component_repairs = (
                aggregate_solution(flow_rows, repair_rows, component_filter)
            )
            if not component_flows and not component_repairs:
                continue
            draw_solution(
                component_dir / f"{component_slug(component_id)}.png",
                f"Solution Overlay: {component_id}",
                nodes,
                arcs,
                demand_rows,
                component_flow_totals,
                component_repair_totals,
                component_flows,
                component_repairs,
                component_id,
            )


if __name__ == "__main__":
    main()
