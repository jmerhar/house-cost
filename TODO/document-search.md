# Full-text search for documents

The documents page searches titles, notes, file names and the extracted text with SQL `LIKE`.
That works for a handful of contracts but finds only exact substrings and does not rank results.

- Add an SQLite FTS5 table over a document's title, notes and text, kept in step on upload, edit
  and delete (triggers or the routes), with a migration that fills it for existing documents.
- Search with FTS5's `MATCH`, ranked by `bm25`, with snippets from `snippet()` for the excerpt.
- Portuguese text: check the tokenizer handles accents (`unicode61 remove_diacritics 2`), so
  "pre-aviso" finds "pré-aviso".
