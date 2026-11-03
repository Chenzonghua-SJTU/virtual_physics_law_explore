# Five-world real Agent benchmark

One scheduled attempt per world; incomplete and failed sessions remain in the comparison. Local acceptance and prediction error are reported separately; no success threshold is imposed.

| World | Run | Status / reason | Calls | Tokens | Energy used | Submitted law | Position RMSE | Velocity RMSE | Wall seconds |
|---|---|---|---:|---:|---:|---|---:|---:|---:|
| world_1 | web-20261102-085517-530d06fa | submitted / submission_accepted_locally | 6 | 155549 | 14 | law_1 | 5.6342158416727564e-08 | 2.928246650018936e-08 | 101.03 |
| world_2 | web-20261102-085658-0e954438 | submitted / submission_accepted_locally | 7 | 185240 | 18 | law_1 | 4.570964604968908e-08 | 2.8635974360499526e-08 | 131.31 |
| world_3 | web-20261102-085910-c1170f82 | submitted / submission_accepted_locally | 8 | 360393 | 24 | law_5 | 3.663498788958161e-08 | 2.9884996162245665e-08 | 211.48 |
| world_4 | web-20261102-090242-aaae4dd6 | submitted / submission_accepted_locally | 7 | 230559 | 14 | law_1 | 8.81684291989046e-08 | 2.829774591467939e-08 | 144.08 |
| world_5 | web-20261102-090506-d09ffce3 | submitted / submission_accepted_locally | 7 | 214511 | 18 | law_1 | 3.7045292959745946e-08 | 2.698899567529417e-08 | 181.23 |

Full law expressions, configurations, prompt hashes and evaluation status are in summary.json and manifest.json.
A missing RMSE is not a zero error. No failed session is replaced by a rerun or a manually supplied law.
