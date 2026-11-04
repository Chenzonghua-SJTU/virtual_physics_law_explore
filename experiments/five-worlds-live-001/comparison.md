# Five-world real Agent benchmark

One scheduled attempt per world; incomplete and failed sessions remain in the comparison. Local acceptance and prediction error are reported separately; no success threshold is imposed.

| World | Run | Status / reason | Calls | Tokens | Energy used | Submitted law | Position RMSE | Velocity RMSE | Wall seconds |
|---|---|---|---:|---:|---:|---|---:|---:|---:|
| world_1 | web-20261102-083147-a56de780 | submitted / submission_accepted_locally | 3 | 59159 | 6 | law_1 | 6.863579805373461e-08 | 3.6898844044141185e-08 | 60.48 |
| world_2 | web-20261102-083248-55995e24 | incomplete / model_finish_length | 1 | 12625 | 0 | — | — | — | 48.31 |
| world_3 | web-20261102-083336-2d512eb2 | incomplete / model_finish_length | 1 | 12630 | 0 | — | — | — | 48.27 |
| world_4 | web-20261102-083425-4685a883 | incomplete / model_token_budget_exhausted | 14 | 217816 | 8 | — | — | — | 100.96 |
| world_5 | web-20261102-083606-55c3572f | incomplete / model_finish_length | 1 | 12635 | 0 | — | — | — | 50.3 |

Full law expressions, configurations, prompt hashes and evaluation status are in summary.json and manifest.json.
A missing RMSE is not a zero error. No failed session is replaced by a rerun or a manually supplied law.
