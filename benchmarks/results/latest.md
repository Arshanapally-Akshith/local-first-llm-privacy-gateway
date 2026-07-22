# Phase 5 Benchmark Results

Commit: `cb0e7f219496fcfb7565108139ef0abc6f3f8b1e`

Dataset size: 2860 examples (`benchmarks/data/dataset.jsonl` — see `benchmarks/data/DATASET_CARD.md`)

Per-entity precision / recall / F1, exact-span exact-type criterion (`docs/DECISIONS.md`, 2026-07-22). Rows where a baseline beats another arm are not removed.

## Arm 1 -- Presidio (stock)

| Entity Type | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| AADHAAR | 0.000 | 0.000 | 0.000 | 495 |
| ADDRESS | 0.000 | 0.000 | 0.000 | 275 |
| CARD | 1.000 | 1.000 | 1.000 | 330 |
| EMAIL | 1.000 | 1.000 | 1.000 | 330 |
| IFSC | 0.000 | 0.000 | 0.000 | 165 |
| ORG | 0.000 | 0.000 | 0.000 | 440 |
| PAN | 0.000 | 0.000 | 0.000 | 330 |
| PERSON | 0.356 | 0.755 | 0.484 | 825 |
| PHONE | 0.939 | 1.000 | 0.969 | 385 |
| UPI | 0.000 | 0.000 | 0.000 | 330 |
| VEHICLE_REG | 0.000 | 0.000 | 0.000 | 330 |

## Arm 2 -- Presidio + custom recognizers

| Entity Type | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| AADHAAR | 0.974 | 1.000 | 0.987 | 495 |
| ADDRESS | 0.000 | 0.000 | 0.000 | 275 |
| CARD | 1.000 | 1.000 | 1.000 | 330 |
| EMAIL | 1.000 | 1.000 | 1.000 | 330 |
| IFSC | 1.000 | 1.000 | 1.000 | 165 |
| ORG | 0.000 | 0.000 | 0.000 | 440 |
| PAN | 1.000 | 1.000 | 1.000 | 330 |
| PERSON | 0.356 | 0.755 | 0.484 | 825 |
| PHONE | 0.939 | 1.000 | 0.969 | 385 |
| UPI | 1.000 | 1.000 | 1.000 | 330 |
| VEHICLE_REG | 1.000 | 1.000 | 1.000 | 330 |

## Arm 3 -- Presidio + custom recognizers + GLiNER backend

| Entity Type | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| AADHAAR | 0.974 | 1.000 | 0.987 | 495 |
| ADDRESS | 0.982 | 0.989 | 0.986 | 275 |
| CARD | 1.000 | 1.000 | 1.000 | 330 |
| EMAIL | 1.000 | 1.000 | 1.000 | 330 |
| IFSC | 1.000 | 1.000 | 1.000 | 165 |
| ORG | 0.458 | 0.941 | 0.617 | 440 |
| PAN | 1.000 | 1.000 | 1.000 | 330 |
| PERSON | 0.621 | 0.938 | 0.747 | 825 |
| PHONE | 0.939 | 1.000 | 0.969 | 385 |
| UPI | 1.000 | 1.000 | 1.000 | 330 |
| VEHICLE_REG | 1.000 | 1.000 | 1.000 | 330 |

## Arm 4 -- Our cascade

| Entity Type | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| AADHAAR | 1.000 | 1.000 | 1.000 | 495 |
| ADDRESS | 1.000 | 0.989 | 0.995 | 275 |
| CARD | 1.000 | 1.000 | 1.000 | 330 |
| EMAIL | 1.000 | 1.000 | 1.000 | 330 |
| IFSC | 1.000 | 1.000 | 1.000 | 165 |
| ORG | 0.521 | 0.941 | 0.670 | 440 |
| PAN | 1.000 | 1.000 | 1.000 | 330 |
| PERSON | 0.741 | 0.938 | 0.828 | 825 |
| PHONE | 1.000 | 1.000 | 1.000 | 385 |
| UPI | 1.000 | 1.000 | 1.000 | 330 |
| VEHICLE_REG | 1.000 | 1.000 | 1.000 | 330 |

