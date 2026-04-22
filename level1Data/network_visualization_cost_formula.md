# Repair Cost Formula

Only `LRU_*` and `LRU_*_*` components are repairable at `--complexity 1`. Shared `PART_*` items are used to build repairs but are not themselves repair options.

## Component Cost Table
| Component Class | Value | Meaning |
| --- | --- | --- |
| `sru` | 18 | Base repair cost for an `SRU` |
| `lru` | 24 | Base repair cost for an `LRU` |

## Child Combination Cost Table
| Child Class | Value | Meaning |
| --- | --- | --- |
| child `part` | 14.0 | Combination cost per required `PART` child |
| child `sru` | 6.0 | Combination cost per required `SRU` child |

## Location Multiplier Table
| Location Type | Multiplier |
| --- | --- |
| `specialized_shop` | 1.4 |
| `local_shop` | 1.2 |
| `regional_warehouse` | 1.0 |
| `central_depot` | 0.85 |

## Formula
```text
repair_cost = round(base_repair_cost + combination_cost)
repair_cost_multiplier = location_multiplier
```

```text
base_repair_cost = repair_base_cost_by_class[component_class]
```

```text
combination_cost = sum(child_combination_cost for each BOM child)
```

```text
if child is SRU:
    child_combination_cost = 6.0 * quantity_required

if child is PART:
    child_combination_cost = 14.0 * quantity_required
```

