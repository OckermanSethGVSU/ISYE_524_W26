# Solution Summary

- data dir: `level3data`
- output dir: `level3output`
- total demand qty: `11`
- total shipped qty: `38`
- total repaired qty: `10`
- active components: `4`
- timesteps: `1, 2, 3, 4`

## Component Totals

| component | shipped_qty | repaired_qty |
| --- | ---: | ---: |
| LRU_2 | 20 | 6 |
| LRU_2_2 | 3 | 0 |
| LRU_3 | 6 | 1 |
| LRU_5 | 9 | 3 |

## Timestep Totals

| timestep | shipped_qty | repaired_qty |
| --- | ---: | ---: |
| 1 | 20 | 5 |
| 2 | 7 | 2 |
| 3 | 8 | 2 |
| 4 | 3 | 1 |

## Demand By Customer

| node | demand_qty |
| --- | ---: |
| CUST_1 | 3 |
| CUST_2 | 2 |
| CUST_3 | 5 |
| CUST_4 | 1 |

## Validation

- All flow arcs and repair nodes matched the paired data files.
