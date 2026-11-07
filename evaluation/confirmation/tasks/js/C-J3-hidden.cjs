'use strict'
// Adapted from PostCSS's MIT-licensed upstream regressions in d1518afd.
const assert = require('node:assert/strict')
const path = require('node:path')
const subject = path.resolve(process.argv[2])
const postcss = require(path.join(subject, 'lib/postcss.js'))
const Stringifier = require(path.join(subject, 'lib/stringifier.js'))
const depth = 6000
const css = 'a{'.repeat(depth) + 'color:red' + '}'.repeat(depth)
const root = postcss.parse(css)
assert.equal(root.toString(), css)
assert.equal(root.clone().toString(), css)
assert.equal(postcss.fromJSON(root.toJSON()).toString(), css)
let count = 0
root.walk(() => { count += 1 })
assert.equal(count, depth + 1)
let visited = 0
const plugin = {postcssPlugin:'confirmation-deep-changer',Declaration(decl) { decl.value = 'blue'; visited += 1 }}
assert.equal(postcss([plugin]).process(postcss.parse(css), {from:undefined}).css,
  'a{'.repeat(depth) + 'color:blue' + '}'.repeat(depth))
assert.equal(visited, 2)
class CustomStringifier extends Stringifier {rule(node) {super.rule(node)}}
let formatted = ''
new CustomStringifier(part => {formatted += part}).stringify(postcss.parse('a{color:black};@media screen{b{}}'))
assert.equal(formatted,'a{color:black};@media screen{b{}}')
const custom = new postcss.Root()
custom._cache = [1,{toJSON:()=>'custom'}]
custom._node = new postcss.Rule({selector:'a'})
assert.deepEqual(custom.toJSON(),{_cache:[1,'custom'],_node:{nodes:[],raws:{},selector:'a',type:'rule'},inputs:[],nodes:[],raws:{},type:'root'})
console.log('C-J3 held-out assertions: 8 passed')
