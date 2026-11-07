// Adapted from markdown-it's MIT-licensed upstream regression assertions, 974e2d7.
import assert from 'node:assert/strict'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
const { default: markdownit } = await import(pathToFileURL(path.join(path.resolve(process.argv[2]), 'src/index.ts')).href)
const md = markdownit()
const cases = [
  ['![a \\* b](/u)', '<p><img src="/u" alt="a * b"></p>\n'],
  ['![a &amp; b](/u)', '<p><img src="/u" alt="a &amp; b"></p>\n'],
  ['![a &lt; b](/u)', '<p><img src="/u" alt="a &lt; b"></p>\n'],
  ['![a \\* *b* &amp; c](/u)', '<p><img src="/u" alt="a * b &amp; c"></p>\n'],
  ['before ![x \\! &#38; **y**](/u) after', '<p>before <img src="/u" alt="x ! &amp; y"> after</p>\n'],
  ['![plain](/u "title")', '<p><img src="/u" alt="plain" title="title"></p>\n'],
  ['ordinary a \\* *b* &amp; c', '<p>ordinary a * <em>b</em> &amp; c</p>\n']
]
for (const [input, expected] of cases) assert.equal(md.render(input), expected, input)
const image = md.parseInline('![a \\* *b* &amp; c](/u)', {})[0].children.find(token => token.type === 'image')
assert.deepEqual(image.children.map(token => token.type), ['text', 'em_open', 'text', 'em_close', 'text'])
assert.deepEqual(image.children.map(token => token.content), ['a * ', '', 'b', '', ' & c'])
console.log(`C-J2 held-out assertions: ${cases.length + 2} passed`)
