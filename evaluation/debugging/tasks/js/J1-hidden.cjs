'use strict';
// Regression assertions derived from the MIT-licensed upstream fix e279bd7.
// Run externally: node J1-hidden.cjs /path/to/candidate/workspace
const assert = require('node:assert/strict');
const path = require('node:path');
const { isMatch } = require(path.resolve(process.argv[2]));
const cases = [
  ['test/utils', 'test(/utils/**)', undefined, true],
  ['test/utils', 'test?(/utils/**)', undefined, true],
  ['test/utils/file', 'test(/utils/**)', undefined, true],
  ['test/utils/file', 'test?(/utils/**)', undefined, true],
  ['test', 'test(/utils/**)', undefined, false],
  ['test', 'test?(/utils/**)', undefined, true],
  ['test/utils', 'test(/utils/**)', { strictSlashes: true }, false],
  ['test/utils', 'test(/utils/**)/file', undefined, false]
];
for (const [input, pattern, options, expected] of cases) {
  assert.equal(isMatch(input, pattern, options), expected, JSON.stringify({ input, pattern, options }));
}
console.log(`J1 held-out regression assertions: ${cases.length} passed`);
