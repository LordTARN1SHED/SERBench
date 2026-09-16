# Changelog

## 0.1.0 — Initial public interface

- Published the Cal500 and Test500 inference interface aligned with paper v5.6.
- Joined Cal500's recovered candidate assets to the exact released item IDs; preserved candidate membership, order, IDs and excerpts.
- Removed Cal500 candidate construction-source tags and role hints from inference inputs; retained public certificates separately.
- Added loaders, strict prediction validation, reference scoring, a lightweight BM25 starter, and a custom-method scaffold.
- Kept Test500 certificates private; added a GitHub submission form for a separately operated private evaluator, with author-assisted fallback during setup.
- Verified the private scoring, public result-comment delivery, and automatic community feed with a 500-state full-abstention integration test. Added all twelve primary paper summaries separately from community results.

This is a benchmark interface release, not a replacement for the paper's full reproduction archive. No frozen predictions, labels, or paper results were edited.
