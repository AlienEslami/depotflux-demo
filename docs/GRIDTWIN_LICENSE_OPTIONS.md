# GridTwin licence options for owner decision

No option is selected by this document, and no licence is granted. The owner
should confirm software/documentation scope, contribution policy and
third-party notice obligations with qualified counsel before publication.

| Option | Practical fit | Main tradeoff |
|---|---|---|
| MIT | Short, familiar permissive terms for portfolio source and examples | Requires preservation of copyright/licence notice; has a warranty disclaimer but no express patent grant |
| Apache License 2.0 | Permissive use with an express patent grant and patent-termination language | Longer obligations, including licence/notice handling and marking modified files where applicable |
| BSD 3-Clause | Concise permissive terms with a non-endorsement clause | Similar notice/disclaimer approach to MIT and no express patent grant |

Decision questions:

1. Should code and documentation use one licence, or should documentation have
   separate terms?
2. Is an express patent grant important enough to prefer Apache-2.0's longer
   notice process?
3. Who owns each contribution and is authorized to grant the selected terms?
4. Which third-party notices and source/attribution duties must ship with source,
   containers and any binary distribution?

The dependency inventory includes LGPL, MPL, Apache, BSD, MIT, CC and other
terms. Those packages retain their own licences; choosing a permissive project
licence does not replace their conditions. The optional Gurobi cross-check uses
the owner's local academic licence and Gurobi is not installed in the portable
Docker/HiGHS image or included in the project dependency lock.
