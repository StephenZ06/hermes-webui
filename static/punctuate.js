/* Punctuation for dictated text (server Whisper and the browser's own speech
   recognition). Whisper often drops punctuation on short clips and browser
   recognition never adds any, so each dictated piece is tidied before it
   reaches the composer:
     - spoken punctuation becomes symbols ("comma", "full stop", "question
       mark", "exclamation mark", "colon", "semicolon", "new line",
       "new paragraph"); "period" is left alone ("trial period"),
     - sentences and a standalone "i" are capitalised,
     - a missing end mark is added: "?" when the last sentence opens with a
       question word (after an optional "so", "hey", ...), "." otherwise.
   Text that already ends in punctuation is left as it is. `before` is what the
   composer already holds, so a piece that continues a sentence is not
   capitalised. No DOM: node tests load it too. */
(function (root) {
  'use strict';
  var SPOKEN = [
    [/\s*\bnew paragraph\b\s*/gi, '\n\n'],
    [/\s*\bnew ?line\b\s*/gi, '\n'],
    [/\s*\bfull stop\b/gi, '.'],
    [/\s*\bquestion mark\b/gi, '?'],
    [/\s*\bexclamation (?:mark|point)\b/gi, '!'],
    [/\s*\bsemicolon\b/gi, ';'],
    [/\s*\bcolon\b/gi, ':'],
    [/\s*\bcomma\b/gi, ','],
  ];
  var QUESTION = /^(?:(?:so|and|but|hey|hi|hello|ok|okay|well|um|uh|also|then)[,]?\s+)?(?:what|why|how|when|where|who|whom|whose|which|can|could|would|should|shall|will|is|are|am|was|were|do|does|did|have|has|had|may|might|isn't|aren't|don't|doesn't|didn't|won't|wouldn't|can't|couldn't|shouldn't)\b/i;

  function punctuateDictation(text, before) {
    var s = String(text || '').replace(/\s+/g, ' ').trim();
    if (!s) return '';
    SPOKEN.forEach(function (rule) { s = s.replace(rule[0], rule[1]); });
    s = s.replace(/([,.;:?!])(?=[^\s,.;:?!])/g, '$1 ')
      .replace(/[ \t]+\n/g, '\n').replace(/\n[ \t]+/g, '\n')
      .replace(/ {2,}/g, ' ').replace(/,([.?!])/g, '$1').trim();
    s = s.replace(/\bi\b/g, 'I');
    var prev = String(before || '');
    if (!prev.trim() || /[.?!]\s*$/.test(prev) || /\n\s*$/.test(prev)) s = s.charAt(0).toUpperCase() + s.slice(1);
    s = s.replace(/([.?!]\s+|\n+)([a-z])/g, function (m, p, c) { return p + c.toUpperCase(); });
    if (/[A-Za-z0-9)"'’]$/.test(s)) {
      var parts = s.split(/[.?!]\s+|\n+/);
      var last = (parts[parts.length - 1] || s).trim();
      s += QUESTION.test(last) ? '?' : '.';
    }
    return s;
  }

  var api = { punctuateDictation: punctuateDictation };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.HermesPunctuate = api;
}(typeof globalThis !== 'undefined' ? globalThis : this));
