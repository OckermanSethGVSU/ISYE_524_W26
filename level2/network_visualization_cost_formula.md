# Repair Cost And Time Formula

Only `LRU_*` and `LRU_*_*` components are repairable at `--complexity 2`. Shared `PART_*` items are used to build repairs but are not themselves repair options.

## Component Cost Table
| Component Class | Cost Value | Time Value | Meaning |
| --- | --- | --- | --- |
| `sru` | 18 | 8 | Base repair cost/time for an `SRU` |
| `lru` | 24 | 16 | Base repair cost/time for an `LRU` |

## Child Combination Cost Table
| Child Class | Cost Value | Time Value | Meaning |
| --- | --- | --- | --- |
| child `part` | 14.0 | 2.0 | Combination cost/time per required `PART` child |
| child `sru` | 6.0 | 7.0 | Combination cost/time per required `SRU` child |

## Location Multiplier Table
| Location Type | Cost Multiplier | Time Multiplier |
| --- | --- | --- |
| `specialized_shop` | 1.4 | 0.8 |
| `local_shop` | 1.2 | 0.95 |
| `regional_warehouse` | 1.0 | 1.1 |
| `central_depot` | 0.85 | 1.25 |

## Formula
```text
repair_cost = round((base_repair_cost + combination_cost) * location_cost_multiplier)
repair_time = round((base_repair_time + combination_time) * location_time_multiplier)
```

```text
base_repair_cost = repair_base_cost_by_class[component_class]
base_repair_time = repair_base_time_by_class[component_class]
```

```text
combination_cost = sum(child_combination_cost for each BOM child)
combination_time = sum(child_combination_time for each BOM child)
```

```text
if child is SRU:
    child_combination_cost = 6.0 * quantity_required
    child_combination_time = 7.0 * quantity_required

if child is PART:
    child_combination_cost = 14.0 * quantity_required
    child_combination_time = 2.0 * quantity_required
```

Specialized shops are fastest and central depots are slowest.
LRU repair takes longer than SRU repair because `LRU` assembly combines `SRU` children with a higher per-child time than `SRU` assembly uses for `PART` children.

