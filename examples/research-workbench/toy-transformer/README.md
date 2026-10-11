# Own scalar-attention demonstration

Version: own-demo-v1. License: [MIT](../LICENSE).

This is original teaching code, **NOT the paper implementation or an actual paper reproduction**. It is not a full Transformer and does not run training or a translation benchmark. No third-party code is redistributed.

`attention.py:scalar_attention` reads a query, scalar keys/values, and temperature. `config.json` names that symbol and `expected_trace.json`. The expected JSON/CSV trace is hand-computed: a zero query gives equal weights and an output of 3. It is an arithmetic check, not a measured experimental result. The generator only reads/copies these files.

Possible follow-up question: which configuration field changes the weighting when the query is nonzero? Check the symbol and source lines; any automatically suggested paper/code relation remains unreviewed. This exercise supports navigation and handoff testing, not a claim that the published method or result has been reproduced.

The paper's full method, training code, dataset, run settings, checkpoints, and raw results remain absent. See [source records](../source_records.json).
