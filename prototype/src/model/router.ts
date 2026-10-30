// Dijkstra over the CSR graph with an arbitrary non-negative per-edge weight.
import type { Graph } from "./graph";

export interface Step { e: number; fwd: boolean } // fwd: travelling eu -> ev
export interface Tree { src: number; dist: Float64Array; prevEdge: Int32Array; prevNode: Int32Array }

class Heap {
  private ids: number[] = [];
  private keys: number[] = [];
  get size() { return this.ids.length; }
  push(id: number, key: number) {
    const ids = this.ids, keys = this.keys;
    let i = ids.length;
    ids.push(id); keys.push(key);
    while (i > 0) {
      const p = (i - 1) >> 1;
      if (keys[p] <= key) break;
      ids[i] = ids[p]; keys[i] = keys[p]; i = p;
    }
    ids[i] = id; keys[i] = key;
  }
  pop(): [number, number] {
    const ids = this.ids, keys = this.keys;
    const top: [number, number] = [ids[0], keys[0]];
    const lastId = ids.pop()!, lastKey = keys.pop()!;
    const n = ids.length;
    if (n > 0) {
      let i = 0;
      for (;;) {
        const l = 2 * i + 1, r = l + 1;
        let s = i, sk = lastKey;
        if (l < n && keys[l] < sk) { s = l; sk = keys[l]; }
        if (r < n && keys[r] < sk) { s = r; sk = keys[r]; }
        if (s === i) break;
        ids[i] = ids[s]; keys[i] = keys[s]; i = s;
      }
      ids[i] = lastId; keys[i] = lastKey;
    }
    return top;
  }
}

export function dijkstra(g: Graph, src: number, weight: ArrayLike<number>): Tree {
  const dist = new Float64Array(g.n).fill(Infinity);
  const prevEdge = new Int32Array(g.n).fill(-1);
  const prevNode = new Int32Array(g.n).fill(-1);
  const heap = new Heap();
  dist[src] = 0;
  heap.push(src, 0);
  while (heap.size) {
    const [u, d] = heap.pop();
    if (d > dist[u]) continue;
    for (let j = g.adjStart[u]; j < g.adjStart[u + 1]; j++) {
      const e = g.adjEdge[j], v = g.adjTo[j];
      const nd = d + weight[e];
      if (nd < dist[v]) { dist[v] = nd; prevEdge[v] = e; prevNode[v] = u; heap.push(v, nd); }
    }
  }
  return { src, dist, prevEdge, prevNode };
}

export function pathTo(g: Graph, tree: Tree, dst: number): Step[] | null {
  if (!isFinite(tree.dist[dst])) return null;
  const steps: Step[] = [];
  let v = dst;
  while (v !== tree.src) {
    const e = tree.prevEdge[v], u = tree.prevNode[v];
    steps.push({ e, fwd: g.eu[e] === u });
    v = u;
  }
  return steps.reverse();
}

export function sameSteps(a: Step[], b: Step[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i].e !== b[i].e) return false;
  return true;
}
