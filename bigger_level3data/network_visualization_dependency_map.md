# Component Dependency Map

`*` marks a shared final-level part. `[S]` marks a specialized-only part.

```text
LRU_1
|-- LRU_1_1 x1
    |-- PART_10* x2
    |-- PART_13*[S] x2
    `-- PART_14* x1
`-- LRU_1_2 x1
    |-- PART_2* x3
    |-- PART_17* x2
    `-- PART_18* x3
LRU_2
|-- LRU_2_1 x2
    |-- PART_1*[S] x1
    |-- PART_2* x3
    `-- PART_8* x1
`-- LRU_2_2 x2
    |-- PART_1*[S] x1
    |-- PART_17* x3
    `-- PART_20* x3
LRU_3
|-- LRU_3_1 x2
    |-- PART_14* x2
    |-- PART_16* x2
    `-- PART_20* x3
`-- LRU_3_2 x2
    |-- PART_1*[S] x2
    |-- PART_4* x1
    `-- PART_16* x3
LRU_4
|-- LRU_4_1 x1
    |-- PART_4* x2
    |-- PART_20* x2
    `-- PART_22*[S] x3
`-- LRU_4_2 x1
    |-- PART_6* x2
    |-- PART_8* x1
    `-- PART_13*[S] x3
LRU_5
|-- LRU_5_1 x1
    |-- PART_1*[S] x1
    |-- PART_6* x2
    `-- PART_7* x3
`-- LRU_5_2 x2
    |-- PART_6* x2
    |-- PART_12*[S] x3
    `-- PART_21* x1
LRU_6
|-- LRU_6_1 x2
    |-- PART_1*[S] x2
    |-- PART_14* x3
    `-- PART_21* x3
`-- LRU_6_2 x2
    |-- PART_5* x1
    |-- PART_10* x2
    `-- PART_12*[S] x2
```
