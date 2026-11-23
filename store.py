"""Read only configured named graph; writes only through explicit CLI import."""
import os
from urllib.parse import urlparse
import httpx
from rdflib import Graph, URIRef
DEMO_GRAPH='https://example.org/grid-demo'

def config():
    endpoint=os.getenv('SPARQL_QUERY_URL','')
    graph=os.getenv('SPARQL_GRAPH',DEMO_GRAPH)
    for url in [endpoint,graph]:
        if url and (urlparse(url).scheme not in ('http','https') or any(c in url for c in '<>"{}\\\n\r ')):
            raise ValueError('SPARQL 配置必须是有效 HTTP(S) URL')
    return endpoint,graph

def headers():
    token=os.getenv('SPARQL_BEARER_TOKEN')
    return {'Authorization':f'Bearer {token}'} if token else {}

def fetch():
    endpoint,graph=config()
    if not endpoint: raise ValueError('尚未配置 SPARQL_QUERY_URL')
    query=f'CONSTRUCT {{ ?s ?p ?o }} WHERE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }}'
    with httpx.Client(timeout=15,follow_redirects=False) as client:
        r=client.post(endpoint,data={'query':query},headers={**headers(),'Accept':'text/turtle'})
        r.raise_for_status()
    if len(r.content)>10_000_000: raise ValueError('远程图超过 Demo 的 10MB 限制')
    g=Graph(); g.parse(data=r.text,format='turtle')
    if not len(g): raise ValueError('配置的命名图为空，请先显式导入 Demo 数据')
    return g

if __name__=='__main__':
    import argparse
    from engine import local_graph
    p=argparse.ArgumentParser(); p.add_argument('action',choices=['check','import-demo']); p.add_argument('--confirm-demo-write',action='store_true'); args=p.parse_args()
    if args.action=='check': print('读取成功，三元组数:',len(fetch()))
    else:
        if not args.confirm_demo_write: p.error('必须指定 --confirm-demo-write；仅向独立 Demo 命名图追加数据')
        _,graph=config()
        if graph!=DEMO_GRAPH: p.error('导入仅允许默认独立 Demo 命名图，避免写入业务图')
        endpoint=os.getenv('SPARQL_UPDATE_URL','')
        if urlparse(endpoint).scheme not in ('http','https'): p.error('请设置 SPARQL_UPDATE_URL')
        triples=local_graph().serialize(format='nt')
        update=f'INSERT DATA {{ GRAPH <{graph}> {{ {triples} }} }}'
        with httpx.Client(timeout=30,follow_redirects=False) as c:
            r=c.post(endpoint,data={'update':update},headers=headers()); r.raise_for_status()
        print('已追加 Demo 数据到独立命名图；没有删除或清空数据。')
