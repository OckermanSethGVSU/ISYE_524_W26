# Component Dependency Map

`*` marks a shared final-level part. `[S]` marks a specialized-only part.

```text
LRU_1
|-- LRU_1_1 x2
    |-- PART_6* x2
    |-- PART_9* x2
    `-- PART_13* x2
`-- LRU_1_2 x2
    |-- PART_7* x2
    |-- PART_8*[S] x3
    `-- PART_10* x3
LRU_2
|-- LRU_2_1 x1
    |-- PART_2*[S] x1
    |-- PART_9* x3
    `-- PART_10* x1
`-- LRU_2_2 x1
    |-- PART_2*[S] x1
    |-- PART_7* x3
    `-- PART_17* x1
LRU_3
|-- LRU_3_1 x1
    |-- PART_1* x1
    |-- PART_3*[S] x3
    `-- PART_4* x1
`-- LRU_3_2 x1
    |-- PART_1* x1
    |-- PART_6* x3
    `-- PART_7* x1
LRU_4
|-- LRU_4_1 x1
    |-- PART_8*[S] x2
    |-- PART_10* x1
    `-- PART_11*[S] x2
`-- LRU_4_2 x2
    |-- PART_5* x1
    |-- PART_8*[S] x3
    `-- PART_13* x1
LRU_5
|-- LRU_5_1 x2
    |-- PART_3*[S] x2
    |-- PART_11*[S] x2
    `-- PART_16* x2
`-- LRU_5_2 x1
    |-- PART_2*[S] x1
    |-- PART_5* x1
    `-- PART_17* x1
```
