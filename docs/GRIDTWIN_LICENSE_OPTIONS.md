# GridTwin licence decision

Decision: **MIT**, approved by the repository owner on 2026-09-14 for the
software and documentation in this product snapshot.

The decisive provenance fact is that the retained Agentic-Aggregator upstream
is already MIT-licensed as `Copyright (c) 2026 The Agentic-Aggregator authors`.
GridTwin therefore preserves that exact copyright and permission notice in the
root `LICENSE`, avoiding an unnecessary second permissive licence over the
inherited optimization core. MIT remains familiar and low-friction for a
portfolio demonstrator. It does not provide Apache-2.0's express patent grant.

| Option | Practical fit | Main tradeoff |
|---|---|---|
| **MIT — selected** | Short, familiar permissive terms matching the retained upstream | Requires preservation of copyright/licence notice; has a warranty disclaimer but no express patent grant |
| Apache License 2.0 | Permissive use with an express patent grant and patent-termination language | Longer obligations, including licence/notice handling and marking modified files where applicable |
| BSD 3-Clause | Concise permissive terms with a non-endorsement clause | Similar notice/disclaimer approach to MIT and no express patent grant |

Decision record:

1. Software and project documentation use one MIT licence.
2. The inherited upstream notice is preserved verbatim.
3. Dependencies and benchmark resources retain their own terms; they are not
   relicensed by the project `LICENSE`.
4. Future contributors must submit work on the understanding that it is
   distributed under MIT; the project does not require copyright assignment.

The dependency inventory includes LGPL, MPL, Apache, BSD, MIT, CC and other
terms. Those packages retain their own licences; choosing a permissive project
licence does not replace their conditions. The optional Gurobi cross-check uses
the owner's local academic licence and Gurobi is not installed in the portable
Docker/HiGHS image or included in the project dependency lock.
