'use strict';
// Regression assertions derived from the MIT-licensed upstream fix f201165.
const assert = require('node:assert/strict');
const path = require('node:path');
const scan = require(path.join(path.resolve(process.argv[2]), 'lib/scan.js'));
const cases = [
  ['', ['']], ['*', ['*']], ['.*', ['.*']], ['**', ['**']], ['foo', ['foo']],
  ['!foo', ['foo']], ['foo*', ['foo*']], ['{1..9}', ['{1..9}']], ['c!(.)z', ['c!(.)z']],
  ['(b|a).(a)', ['(b|a).(a)']], ['+(a|b\\[)*', ['+(a|b\\[)*']],
  ['@(a|b).md', ['@(a|b).md']], ['(a/b)', ['(a/b)']], ['(a\\b)', ['(a\\b)']],
  ['foo\\[a\\/]', ['foo\\[a\\/]']], ['foo[/]bar', ['foo[/]bar']],
  ['/', ['', '']], ['/*', ['', '*']], ['/a', ['', 'a']], ['/a/b', ['', 'a', 'b']],
  ['/a/b/', ['', 'a', 'b', '']], ['*/', ['*', '']], ['./', ['']],
  ['/dev\\/@(tcp|udp)\\/*\\/*', ['', 'dev\\/@(tcp|udp)\\/*\\/*']],
  ['!(!(bar)/baz)', ['!(!(bar)/baz)']], ['(!(b/a))', ['(!(b/a))']],
  ['a/((b)/c)/d', ['a', '((b)/c)', 'd']], ['a/(b\\)/c)/d', ['a', '(b\\)/c)', 'd']],
  ['(a|b)/c', ['(a|b)', 'c']], ['./directory/(a|b)/*.js', ['directory', '(a|b)', '*.js']],
  ['a/@(!(b)/c)/*.js', ['a', '@(!(b)/c)', '*.js']]
];
for (const [pattern, expected] of cases) {
  assert.deepEqual(scan(pattern, { parts: true }).parts, expected, pattern);
}
const tokenCases = [
  ['/', ['', '']], ['/a/b', ['', 'a', 'b']], ['!foo', ['foo']],
  ['./!a/b', ['a', 'b']], ['a/b/*/c', ['a', 'b', '*', 'c']]
];
for (const [pattern, expected] of tokenCases) {
  assert.deepEqual(scan(pattern, { tokens: true }).parts, expected, `tokens: ${pattern}`);
}
console.log(`J2 held-out regression assertions: ${cases.length + tokenCases.length} passed`);
