# Solution Summary

- data dir: `level3data`
- output dir: `level3output`
- total demand qty: `11`
- total shipped qty: `23`
- total repaired qty: `6`
- active components: `2`
- timesteps: `1, 2, 3, 4`

## Component Totals

| component | shipped_qty | repaired_qty |
| --- | ---: | ---: |
| LRU_2 | 20 | 6 |
| LRU_2_2 | 3 | 0 |

## Timestep Totals

| timestep | shipped_qty | repaired_qty |
| --- | ---: | ---: |
| 1 | 17 | 4 |
| 2 | 1 | 1 |
| 3 | 5 | 1 |
| 4 | 0 | 0 |

## Demand By Customer

| node | demand_qty |
| --- | ---: |
| CUST_1 | 3 |
| CUST_2 | 2 |
| CUST_3 | 5 |
| CUST_4 | 1 |

## Validation

- All flow arcs and repair nodes matched the paired data files.
