'use strict';
// Regression assertions derived from the MIT-licensed upstream fix ab8bc4d.
const assert = require('node:assert/strict');
const path = require('node:path');
const picomatch = require(path.resolve(process.argv[2]));
const cases = [
  ['foo\\bar.js', 'bar.js', { basename: true, windows: true }, true],
  ['a\\b\\c\\d.md', '*.md', { matchBase: true, windows: true }, true],
  ['x\\y\\acb', 'a?b', { matchBase: true, windows: true }, true],
  ['x\\y\\acb', 'a?z', { matchBase: true, windows: true }, false],
  ['a/b\\c.js', '*.js', { matchBase: true, windows: true }, true],
  ['foo/bar.js', 'bar.js', { basename: true }, true],
  ['foo\\bar.js', 'bar.js', { basename: true, windows: false }, false]
];
for (const [input, pattern, options, expected] of cases) {
  assert.equal(picomatch.isMatch(input, pattern, options), expected, JSON.stringify({ input, pattern, options }));
}
assert.equal(picomatch.matchBase('foo\\bar.js', 'bar.js', { windows: true }), true);
assert.equal(picomatch.matchBase('foo\\bar.js', 'bar.js', { windows: false }), false);
assert.equal(picomatch.matchBase('foo\\bar.js', /^bar\.js$/, { windows: true }), true);
console.log(`J3 held-out regression assertions: ${cases.length + 3} passed`);
