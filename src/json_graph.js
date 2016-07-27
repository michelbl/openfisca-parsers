#! /usr/bin/env node

import read from 'read-file-stdin'

function is_ofnode(value) {
  return ((value instanceof Object) && ('type' in value));
}

function of_equality(a, b) {
  console.assert (is_ofnode(a));
  console.assert (is_ofnode(b));

  if (Object.keys(a).length != Object.keys(b).length) {
    return false;
  }

  for (var k in a) {
    if (!(k in b)) {
      return false;
    }

    if (is_ofnode(a.k)) {
      if (!is_ofnode(b.k)) {
        return false;
      }
      if (!of_equality(a.k, b.k)) {
        return false;
      }
    } else if (a.k instanceof Array) {
      if (!(b.k instanceof Array)) {
        return false;
      }
      if (a.k.length != b.k.length) {
        return false;
      }
      for (var i = 0; i < a.k.length; i++) {
        if (is_ofnode(a.k[i])) {
          if (!(is_ofnode(b.k[i]))) {
            return false;
          }
          if (!of_equality(a.k[i], b.k[i])) {
            return false;
          }
        } else {
          if (a.k[i] != b.k[i]) {
            return false;
          }
        }
      }
    } else {
      if (a.k !== b.k) {
        return false;
      }
    }
  }
  return true;
}


function serialize(input_nodes) {
  let visited_nodes = [];
  let output_nodes = [];
  let edges = [];

  let append_edge = edge => {
    /*
    Mutates `edges` in outer scope.

    Workaround due to a limitation of graphlib npm module which has only `setEdge` method.
    Consequence: it is not possible to add many edges having the same source and target.
    Even if graphviz supports it.
    See: https://github.com/cpettitt/graphlib/blob/master/lib/graph.js#L353
    */
    for (var i = 0; i < edges.length; i++) {
      let edge1 = edges[i];
      if ((edge['source'] === edge1['source']) &&
          (edge['target'] === edge1['target']))
      {
        edge1['label'] += '\n' + edge['label'];
        return;
      }
    }
    edges.push(edge);
  }

  let ShortIdGenerator = function* (object) {
    let next_shortid = 0;

    while (true) {
      yield next_shortid++;
    }
  }

  let short_id_generator = ShortIdGenerator();

  let visit = ofnode => {
    console.assert (is_ofnode(ofnode));

    if ('_id' in ofnode) {
      return;
    }

    let ofnode_id = short_id_generator.next().value
    let jgfnode = Object.assign({}, ofnode);
    jgfnode['id'] = ofnode_id;
    ofnode['_id'] = ofnode_id;
    visited_nodes.push(ofnode);

    for (let key in ofnode) {
      let value = ofnode[key];
      if (value instanceof Array) {
        if (key !== 'path') {
          delete jgfnode[key];
          for (var i = 0; i < value.length; i++) {
            let item = value[i];
            if (is_ofnode(item)) {
              visit(item);
              append_edge({
                'source': ofnode_id,
                'target': item._id,
                'label': key + '[' + i + ']',
                });
            }
          }
        }
      } else if (is_ofnode(value)) {
        delete jgfnode[key];
        visit(value);
        let edge = {
          'source': ofnode_id,
          'target': value._id,
          'label': key,
          };
        // if ofnode['type'] == 'ValueForPeriod' and key == 'period':
        //     edge['color'] = 'red'
        append_edge(edge);
      }
    }
    output_nodes.push(jgfnode);
  }

  if (input_nodes instanceof Array) {
    for (var i = 0; i < root_ofnode.length; i++) {
      item = input_nodes[i];
      visit(item);
    }
  } else {
    visit(input_nodes);
  }

  // Remove _id keys in input objects
  for (var i = 0; i < visited_nodes.length; i++) {
    let visited_node = visited_nodes[i];
    delete visited_node['_id'];
  }

  return {
      'graph': {
          'directed': true,
          'nodes': output_nodes,
          'edges': edges,
          },
      }
}


function unserialize(json_graph) {
  console.assert(Object.keys(json_graph).length == 1);
  console.assert('graph' in json_graph);
  let graph = json_graph.graph;

  console.assert(graph.directed);

  let edges = graph.edges;
  let input_nodes = graph.nodes;

  let output_nodes = {};

  for (var i = 0; i < input_nodes.length; i++) {
    let input_node = input_nodes[i];
    let node_id = input_node.id;

    let output_node = Object.assign({}, input_node);
    delete output_node['id'];

    output_nodes[node_id] = output_node;
  }

  for (var i = 0; i < edges.length; i++) {
    let edge = edges[i];
    let source_id = edge.source;
    let target_id = edge.target;
    let label = edge.label;

    let source_node = output_nodes[source_id];
    let target_node = output_nodes[target_id];

    if (['input_period', 'output_period', 'operand', 'parameter',
         'instant', 'variable', 'period', 'formula', 'value'].includes(label)) {
      source_node[label] = target_node;
    } else {
      let regexp = /^operands\[([0-9]+)\]/;
      let regexp_result = regexp.exec(label);
      if (regexp_result) {
        let index = parseInt(regexp_result[1]);
        if (!('operands' in source_node)) {
          source_node.operands = [];
        }
        source_node.operands[index] = target_node;
      } else {
        throw 'Unknown label : ' + label;
      }
    }
  }
  return output_nodes;
}


function main(json_buffer) {
  const json_graph1 = JSON.parse(json_buffer);
  let json_string1 = JSON.stringify(json_graph1);

  let nodes1 = unserialize(json_graph1);
  let root_node1 = nodes1[0];

  let json_graph2 = serialize(root_node1);
  let json_string2 = JSON.stringify(json_graph2);

  let nodes2 = unserialize(json_graph2);
  let root_node2 = nodes2[0];

  //console.log(nodes);
  console.log(json_string1);
  console.log(json_string2);
  console.log(of_equality(root_node1, root_node2));
}


read(process.argv[2], (err, buffer) => {
  if (err) { throw err; }

  main(buffer);
});
