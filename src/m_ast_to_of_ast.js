#! /usr/bin/env node

import read from 'read-file-stdin'

import traverse from './traverse'
import mToOpenFiscaVisitor from './visitors/m_to_openfisca'

// Example: jq --slurpfile chap1 json/chap-1.json '. + $chap1[].variables' json/isf.json > json/isf_with_chap1.json

function main (nodes) {
  const moduleNode = {
    type: 'Module',
    regles: nodes
  }
  const state = {debug: false}
  const transformedNode = traverse(mToOpenFiscaVisitor, state, moduleNode)
  console.log(JSON.stringify(transformedNode, null, 2))
}

read(process.argv[2], (err, buffer) => {
  if (err) throw err
  const nodes = JSON.parse(buffer)
  main(nodes)
})