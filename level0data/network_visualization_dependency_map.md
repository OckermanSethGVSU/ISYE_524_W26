# Component Dependency Map

`*` marks a shared final-level part. `[S]` marks a specialized-only part.

```text
LRU_1
|-- LRU_1_1 x2
    |-- PART_1* x2
    |-- PART_5* x2
    `-- PART_11* x2
`-- LRU_1_2 x2
    |-- PART_8* x3
    |-- PART_13* x2
    `-- PART_14*[S] x1
LRU_2
|-- LRU_2_1 x2
    |-- PART_4* x3
    |-- PART_5* x3
    `-- PART_6*[S] x3
`-- LRU_2_2 x1
    |-- PART_2* x3
    |-- PART_3*[S] x3
    `-- PART_4* x2
LRU_3
|-- LRU_3_1 x1
    |-- PART_1* x3
    |-- PART_3*[S] x3
    `-- PART_12* x1
`-- LRU_3_2 x2
    |-- PART_14*[S] x2
    |-- PART_15* x2
    `-- PART_17*[S] x3
LRU_4
|-- LRU_4_1 x1
    |-- PART_5* x2
    |-- PART_6*[S] x1
    `-- PART_12* x1
`-- LRU_4_2 x1
    |-- PART_4* x1
    |-- PART_10* x1
    `-- PART_12* x2
LRU_5
|-- LRU_5_1 x2
    |-- PART_5* x1
    |-- PART_6*[S] x1
    `-- PART_12* x2
`-- LRU_5_2 x2
    |-- PART_1* x2
    |-- PART_12* x2
    `-- PART_16* x3
```
