/* Normalize wildcard queries through the same language pipeline as the index.
 * Material appends a trailing wildcard; Lunr normally skips stemming for it.
 * Load the exact worker URL provided by the installed Material template.
 */
const originalWorker = new URL(self.location.href).searchParams.get("worker");
if (!originalWorker || new URL(originalWorker).origin !== self.location.origin) {
  throw new Error("Search worker must be loaded from this site's origin");
}
importScripts(originalWorker);

lunr.Index.prototype.search = function (queryString) {
  const index = this;
  return index.query(function (query) {
    const parsed = new lunr.Query(index.fields);
    new lunr.QueryParser(queryString, parsed).parse();
    for (const clause of parsed.clauses) {
      const leading = clause.term.startsWith("*") ? "*" : "";
      const trailing = clause.term.endsWith("*") ? "*" : "";
      const word = clause.term.replace(/^\*|\*$/g, "");
      // Preserve embedded wildcard expressions and other Lunr query syntax.
      if ((!leading && !trailing) || word.includes("*")) {
        query.clause(clause);
        continue;
      }
      for (const term of index.pipeline.runString(word, { fields: clause.fields })) {
        query.clause({ ...clause, term: leading + term + trailing, usePipeline: false });
      }
    }
  });
};
