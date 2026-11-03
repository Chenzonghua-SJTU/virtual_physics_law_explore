# Five-world real Agent benchmark

One scheduled attempt per world; incomplete and failed sessions remain in the comparison. Local acceptance and prediction error are reported separately; no success threshold is imposed.

| World | Run | Status / reason | Calls | Tokens | Energy used | Submitted law | Position RMSE | Velocity RMSE | Wall seconds |
|---|---|---|---:|---:|---:|---|---:|---:|---:|
| world_1 | web-20261102-113701-c80b7165 | submitted / submission_accepted_locally | 4 | 47541 | 5 | law_1 | 6.023298852953939e-08 | 3.169458918727722e-08 | 42.38 |
| world_2 | web-20261102-113744-82cc725b | submitted / submission_accepted_locally | 7 | 370530 | 14 | law_2 | 6.389206716262898e-08 | 3.8509855385458405e-08 | 258.6 |
| world_3 | web-20261102-114203-c9da8920 | submitted / submission_accepted_locally | 6 | 197435 | 14 | law_1 | 3.671987477463358e-08 | 2.997682340243599e-08 | 165.45 |
| world_4 | web-20261102-114449-7556d485 | submitted / submission_accepted_locally | 7 | 181053 | 12 | law_1 | 2.3929726197350396e-07 | 1.0145597425362504e-07 | 116.9 |
| world_5 | web-20261102-114646-e4b93b95 | submitted / submission_accepted_locally | 6 | 209593 | 32 | law_2 | 1.7006335186353244e-07 | 1.2191120251415792e-07 | 175.57 |

Full law expressions, configurations, prompt hashes and evaluation status are in summary.json and manifest.json.
A missing RMSE is not a zero error. No failed session is replaced by a rerun or a manually supplied law.
