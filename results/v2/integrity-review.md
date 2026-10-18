# Independent read-only review

Native Luna/medium agent `/root/v2_integrity_review` reviewed source, manifests and integration claims, without reading candidate answers or gold and without modifying frozen candidates.

No concrete cross-scope, forged-metadata, symlink or stale-revision exploit was found in the frozen runnable adapters. This is a bounded code review, with a trusted immutable synthetic corpus; path checks do not provide an OS-level defense against a concurrent filesystem adversary.

The frozen low-level grader's negative branch checks only an abstention flag and valid citations. Final scoring therefore uses `benchkit/v2/quality.py` and requires an explicit coordinator content review for every negative answer. Unsupported claims cannot receive final credit merely by setting `abstain:true`. The post-submission summary catches malformed answer/citation exceptions as invalid submissions. The frozen low-level code remains intact for audit.

The frozen retrieval grader's `precision_at_5` means correct hits divided by returned hits. Postprocessing labels that value `precision_among_returned_at_most_5` and separately computes conventional precision with a denominator of five. Both exclude negative questions, whose empty-hit rate is reported separately.

RSS is the process lifetime high-water mark, not per-question allocation or total candidate memory. Kernel block-I/O counters do not establish physical bytes. First/reused adapter labels do not establish physically cold/warm cache. Both guarded and adapter-only latency are reported. Basic Memory's adapter-only latency includes child startup and query-local indexing; its parent RSS excludes child peak memory.

The review confirmed the documented engine boundaries: real neural Qdrant, real custom MCP over Basic Memory SDK, real Cognee add-only storage with graph/vector indexing blocked, and Graphiti encoder exercised with extraction/temporal integration skipped. No graph quality result is inferred.
