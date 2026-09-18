# Changelog

## Canonical paper link

- Pointed public paper links to the unversioned [arXiv record](https://arxiv.org/abs/2609.20050) so later manuscript revisions appear at the same URL.
- Removed the duplicate PDF from this benchmark repository; its prior copy remains recoverable in Git history.

## Paper and artifact alignment — v5.11

- Updated the linked arXiv manuscript and benchmark overview figure to paper v5.11.
- Confirmed that the twelve primary Test500 result summaries and public benchmark data remain unchanged in the v5.7 supplementary package.
- The v5.7 supplementary package omits the Paired27 dataset and paired-result archives; neither is part of this public benchmark interface.
- Preserved the frozen `serbench-public-v1-v5.6` scoring-contract identifier; this is a data-interface version, not the manuscript version.

## 0.1.0 — Initial public interface

- Published the Cal500 and Test500 inference interface aligned with paper v5.6.
- Joined Cal500's recovered candidate assets to the exact released item IDs; preserved candidate membership, order, IDs and excerpts.
- Removed Cal500 candidate construction-source tags and role hints from inference inputs; retained public certificates separately.
- Added loaders, strict prediction validation, reference scoring, a lightweight BM25 starter, and a custom-method scaffold.
- Kept Test500 certificates private; added a GitHub submission form for a separately operated private evaluator, with author-assisted fallback during setup.
- Verified the private scoring, public result-comment delivery, and automatic community feed with a 500-state full-abstention integration test. Added all twelve primary paper summaries separately from community results.

This is a benchmark interface release, not a replacement for the paper's full reproduction archive. No frozen predictions, labels, or paper results were edited.
