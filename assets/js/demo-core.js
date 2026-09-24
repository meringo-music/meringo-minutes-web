// The demo's arithmetic, no DOM. Every scoreboard number comes from tally(),
// which counts my audit notes in demo.json; none is typed.

export const secondsOf = (ts) => String(ts).split(':').reduce((m, s) => m * 60 + Number(s), 0);

// The app's summary sentences, in order, overview first: each is { h, t? }.
export function keptSentences(app) {
  return [{ h: app.summary.overviewH },
    ...app.summary.sections.flatMap((s) => s.items.flatMap((i) => i.sentences))];
}

export function tally(demo) {
  const audit = demo.site.audit;
  const kept = keptSentences(demo.app).map((s) => audit[s.h]);
  const anchored = kept.filter((a) => a.line != null);
  const asks = demo.app.asks.map((q) => ({ ...audit[q.h], refused: q.refused }));
  const traps = asks.filter((a) => !a.answerable);
  const answerable = asks.filter((a) => a.answerable);
  const n = (list, test) => list.filter(test).length;
  return {
    lineNo: n(anchored, (a) => a.line === 'no'),
    anchored: anchored.length,
    linePartly: n(anchored, (a) => a.line === 'partly'),
    keptPartly: n(kept, (a) => a.transcript === 'partly'),
    kept: kept.length,
    trapsRefused: n(traps, (a) => a.refused),
    traps: traps.length,
    answerableRefused: n(answerable, (a) => a.refused),
    answerable: answerable.length,
    invented: n(asks, (a) => a.invented),
  };
}

// A verdict as words, never colour alone: "Line: no · Transcript: partly" for
// a summary sentence, "Verdict: no · Refused, wrongly" for an answer.
export function verdictText(a, cap) {
  const parts = 'verdict' in a
    ? [`${cap.verdict}: ${a.verdict}`, a.label]
    : [a.line != null && `${cap.line}: ${a.line}`, `${cap.transcript}: ${a.transcript}`];
  return parts.filter(Boolean).join(' · ');
}
