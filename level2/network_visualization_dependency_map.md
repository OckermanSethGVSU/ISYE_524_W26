# Component Dependency Map

`*` marks a shared final-level part. `[S]` marks a specialized-only part.

```text
LRU_1
|-- LRU_1_1 x1
    |-- PART_1* x3
    |-- PART_11* x1
    `-- PART_15* x1
`-- LRU_1_2 x1
    |-- PART_8* x3
    |-- PART_9* x1
    `-- PART_11* x1
LRU_2
|-- LRU_2_1 x1
    |-- PART_3* x1
    |-- PART_12*[S] x1
    `-- PART_17* x3
`-- LRU_2_2 x1
    |-- PART_1* x1
    |-- PART_2*[S] x2
    `-- PART_6* x1
LRU_3
|-- LRU_3_1 x1
    |-- PART_1* x3
    |-- PART_2*[S] x3
    `-- PART_5*[S] x2
`-- LRU_3_2 x2
    |-- PART_1* x3
    |-- PART_8* x3
    `-- PART_10* x3
LRU_4
|-- LRU_4_1 x2
    |-- PART_3* x2
    |-- PART_8* x3
    `-- PART_11* x1
`-- LRU_4_2 x2
    |-- PART_3* x2
    |-- PART_11* x2
    `-- PART_16* x2
LRU_5
|-- LRU_5_1 x1
    |-- PART_2*[S] x1
    |-- PART_3* x1
    `-- PART_9* x1
`-- LRU_5_2 x1
    |-- PART_8* x2
    |-- PART_12*[S] x2
    `-- PART_17* x1
```
