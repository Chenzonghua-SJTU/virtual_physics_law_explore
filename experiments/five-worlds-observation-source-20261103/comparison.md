# Five-world real Agent benchmark

One scheduled attempt per world; incomplete and failed sessions remain in the comparison. Local acceptance and prediction error are reported separately; no success threshold is imposed.

| World | Run | Status / reason | Calls | Tokens | Energy used | Submitted law | Position RMSE | Velocity RMSE | Wall seconds |
|---|---|---|---:|---:|---:|---|---:|---:|---:|
| world_1 | web-20261103-053033-d7ba2865 | submitted / submission_accepted_locally | 3 | 34763 | 2 | law_1 | 6.023298907550687e-08 | 3.169458934722472e-08 | 40.14 |
| world_2 | web-20261103-053114-ce4f01d6 | submitted / submission_accepted_locally | 10 | 375549 | 28 | law_5 | 5.473264439068124e-08 | 3.006861917707942e-08 | 171.81 |
| world_3 | web-20261103-053406-95984ecd | submitted / submission_accepted_locally | 23 | 1497127 | 9 | law_4 | 2.129543495218071 | 1.358614148137722 | 429.27 |
| world_4 | web-20261103-054116-026291f0 | incomplete / model_token_budget_exhausted | 18 | 1585725 | 18 | — | — | — | 682.77 |
| world_5 | web-20261103-055239-d5ff5629 | submitted / submission_accepted_locally | 10 | 293593 | 20 | law_4 | 4.010452675893536e-08 | 3.277821537489508e-08 | 151.51 |

Full law expressions, configurations, prompt hashes and evaluation status are in summary.json and manifest.json.
A missing RMSE is not a zero error. No failed session is replaced by a rerun or a manually supplied law.
