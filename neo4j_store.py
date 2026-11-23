"""Neo4j property graph persistence, RDF semantics remain in RDFLib/OWL RL."""
import os
import hashlib
from urllib.parse import urlparse
from rdflib import Graph, URIRef, BNode, Literal
from neo4j import GraphDatabase
from engine import Grid, local_graph
SCOPE='grid-demo-v1'

def connection():
    uri=os.getenv('NEO4J_URI','bolt://127.0.0.1:7687')
    if urlparse(uri).scheme not in ('bolt','bolt+s','bolt+ssc','neo4j','neo4j+s','neo4j+ssc'):
        raise ValueError('NEO4J_URI 必须是 Bolt/Neo4j 地址')
    user=os.getenv('NEO4J_USERNAME','neo4j'); password=os.getenv('NEO4J_PASSWORD')
    if not password: raise ValueError('请在本机设置 NEO4J_PASSWORD，不要将密码发送到对话')
    return GraphDatabase.driver(uri,auth=(user,password),connection_timeout=10,connection_acquisition_timeout=15,max_transaction_retry_time=10)

def records(g):
    out=[]
    for s,p,o in g:
        row={'s':str(s),'skind':'bnode' if isinstance(s,BNode) else 'uri','p':str(p),'o':str(o),'kind':'literal' if isinstance(o,Literal) else 'bnode' if isinstance(o,BNode) else 'uri','datatype':str(o.datatype or '') if isinstance(o,Literal) else '', 'lang':str(o.language or '') if isinstance(o,Literal) else ''}
        key='\x1f'.join(row[k] for k in ['s','skind','p','o','kind','datatype','lang'])
        row['key']=hashlib.sha256(key.encode()).hexdigest(); out.append(row)
    return out

def decode(rows):
    g=Graph()
    for row in rows:
        s=BNode(row['s']) if row['skind']=='bnode' else URIRef(row['s'])
        if row['kind']=='literal': o=Literal(row['o'],lang=row['lang'] or None,datatype=URIRef(row['datatype']) if row['datatype'] else None)
        elif row['kind']=='bnode': o=BNode(row['o'])
        else: o=URIRef(row['o'])
        g.add((s,URIRef(row['p']),o))
    return g

def fetch():
    with connection() as driver:
        result=driver.execute_query('MATCH (t:GridDemoTriple {scope:$scope}) RETURN t LIMIT 50001',scope=SCOPE,database_=os.getenv('NEO4J_DATABASE','neo4j'),routing_='r')
        rows=[dict(r['t']) for r in result.records]
    if not rows: raise ValueError('Neo4j 中未找到独立 Demo 数据；请先显式执行模拟数据导入')
    if len(rows)>50000: raise ValueError('Demo 三元组超过 50000 条，拒绝截断分析')
    return decode(rows)

def import_demo():
    g=local_graph(); view=Grid(g).view()
    rows=records(g)
    # Single managed transaction for all RDF triples and the visual projection.
    def write(tx):
        tx.run('UNWIND $rows AS row MERGE (t:GridDemoTriple {scope:$scope,key:row.key}) SET t += row',rows=rows,scope=SCOPE).consume()
        tx.run('UNWIND $nodes AS row MERGE (n:GridDemoEntity {scope:$scope,id:row.id}) SET n.label=row.label, n.types=row.types',nodes=view['nodes'],scope=SCOPE).consume()
        tx.run('UNWIND $edges AS row MATCH (a:GridDemoEntity {scope:$scope,id:row.source}), (b:GridDemoEntity {scope:$scope,id:row.target}) MERGE (a)-[:GRID_DEMO_RELATION {scope:$scope,predicate:row.relation}]->(b)',edges=view['edges'],scope=SCOPE).consume()
    with connection() as driver:
        driver.verify_connectivity()
        with driver.session(database=os.getenv('NEO4J_DATABASE','neo4j')) as session: session.execute_write(write)
    return len(rows)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('action',choices=['check','import-demo']); p.add_argument('--confirm-demo-write',action='store_true'); args=p.parse_args()
    if args.action=='import-demo':
        if not args.confirm_demo_write: p.error('导入需要 --confirm-demo-write；仅写入带 GridDemo 标签和独立 scope 的数据')
        print('Demo 三元组已追加：',import_demo())
    else: print('读取成功，三元组数：',len(fetch()))
