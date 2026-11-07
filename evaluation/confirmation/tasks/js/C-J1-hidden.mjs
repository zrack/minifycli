// Adapted from markdown-it's MIT-licensed upstream regression fixture, 5e9b1cc.
import assert from 'node:assert/strict'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
const { default: markdownit } = await import(pathToFileURL(path.join(path.resolve(process.argv[2]), 'src/index.ts')).href)
const md = markdownit()
const cases = [
  ['[foo `bar` baz`', '<p>[foo <code>bar</code> baz`</p>\n'],
  ['![alt `code` x`', '<p>![alt <code>code</code> x`</p>\n'],
  ['[`](``)', '<p><a href="%60%60">`</a></p>\n'],
  ['[`a](/x)``b', '<p><a href="/x">`a</a>``b</p>\n'],
  ['[foo `bar](/url)` baz', '<p>[foo <code>bar](/url)</code> baz</p>\n'],
  ['`one` and ``two ` three``', '<p><code>one</code> and <code>two ` three</code></p>\n'],
  ['[label](/url)', '<p><a href="/url">label</a></p>\n'],
  ['[foo `bar`]', '<p>[foo <code>bar</code>]</p>\n'],
  ['``unclosed ` run', '<p>``unclosed ` run</p>\n'],
  ['[a `b`](/url)', '<p><a href="/url">a <code>b</code></a></p>\n']
]
for (const [input, expected] of cases) assert.equal(md.render(input), expected, input)
console.log(`C-J1 held-out assertions: ${cases.length} passed`)
