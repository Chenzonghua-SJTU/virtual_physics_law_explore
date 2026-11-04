# Five-world real Agent benchmark

One scheduled attempt per world; incomplete and failed sessions remain in the comparison. Local acceptance and prediction error are reported separately; no success threshold is imposed.

| World | Run | Status / reason | Calls | Tokens | Energy used | Submitted law | Position RMSE | Velocity RMSE | Wall seconds |
|---|---|---|---:|---:|---:|---|---:|---:|---:|
| world_1 | web-20261103-073246-1ef99e81 | submitted / submission_accepted_locally | 10 | 228042 | 13 | law_1 | 6.023298959359085e-08 | 3.1694589550869444e-08 | 95.47 |
| world_2 | web-20261103-073422-33fef611 | submitted / submission_accepted_locally | 13 | 465494 | 22 | law_5 | 4.570964552552385e-08 | 2.8635974023187088e-08 | 195.96 |
| world_3 | web-20261103-073739-1962cf75 | submitted / submission_accepted_locally | 12 | 422735 | 13 | law_3 | 3.047326086004267e-08 | 3.024549494111484e-08 | 212.21 |
| world_4 | web-20261103-074112-03c2278b | submitted / submission_accepted_locally | 10 | 597647 | 28 | law_1 | 1.4589346514600036e-06 | 6.091810130367235e-07 | 288.25 |
| world_5 | web-20261103-074601-2e14853c | submitted / submission_accepted_locally | 11 | 478320 | 18 | law_3 | 2.9449225614467083 | 1.9586777203844499 | 249.24 |

Full law expressions, configurations, prompt hashes and evaluation status are in summary.json and manifest.json.
A missing RMSE is not a zero error. No failed session is replaced by a rerun or a manually supplied law.
