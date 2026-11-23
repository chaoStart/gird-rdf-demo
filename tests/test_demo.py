import pytest
from rdflib import RDF, Literal, XSD
from fastapi.testclient import TestClient
from engine import Grid, G, local_graph
from app import app, grid

def test_q1_s1_outage():
    r=Grid().analyze({'S1':'open'})
    assert r['outage_transformers']==['A','B']
    assert r['outage_customers']==['U1','U2'] and r['households']==1200

def test_q2_overload():
    assert Grid().analyze()['overloads']==[{'id':'C','load_kva':500.0,'capacity_kva':400.0}]

def test_q3_transfer():
    r=Grid().transfer(states={'S1':'open'})
    assert r['screening_passed'] and not r['operationally_approved']
    assert r['required_kva']==700 and r['spare_kva']==1500
    assert r['after']['outage_customers']==[]

def test_q4_semantic_inheritance():
    g=Grid().g
    assert (G.S1,RDF.type,G.ElectricalEquipment) in g

def test_q5_downstream():
    g=Grid().g
    assert (G.B,G.downstreamOf,G.X) in g
    query='PREFIX grid: <https://example.org/grid#> SELECT ?c WHERE { ?t grid:downstreamOf+ grid:S1; grid:supplies ?c }'
    assert {str(row.c) for row in g.query(query)}=={str(G.U1),str(G.U2)}

def test_backup_path_prevents_false_outage():
    assert Grid().analyze({'S1':'open','L1':'closed'})['households']==0

def test_parallel_sources_rejected():
    r=Grid().transfer(states={'S1':'closed'})
    assert not r['screening_passed'] and '会形成多电源并列' in r['reasons']

def test_capacity_insufficient():
    g=local_graph(); g.set((G.Y,G.ratedCapacity,Literal(1000,datatype=XSD.decimal)))
    r=Grid(g).transfer(states={'S1':'open'})
    assert not r['screening_passed'] and '备用馈线容量不足' in r['reasons']

def test_fault_cannot_be_restored():
    r=Grid().transfer(states={'S1':'open'},blocked=['B'])
    assert not r['screening_passed']

def test_multi_supply_customer():
    g=local_graph(); g.add((G.C,G.supplies,G.U1))
    r=Grid(g).analyze({'S1':'open'})
    assert r['outage_customers']==['U2'] and r['households']==500

def test_cycle_rejected():
    g=local_graph(); g.add((G.Y,G.connectedTo,G.A))
    assert '会形成环网' in Grid(g).transfer(states={'S1':'open'})['reasons']

def test_missing_and_nan_rejected():
    g=local_graph(); g.remove((G.A,G.currentLoad,None))
    with pytest.raises(ValueError): Grid(g)
    g=local_graph(); g.set((G.A,G.currentLoad,Literal('NaN',datatype=XSD.decimal)))
    with pytest.raises(ValueError): Grid(g)

def test_unknown_switch():
    with pytest.raises(ValueError): Grid().analyze({'not-real':'open'})

def test_maintenance_isolated():
    g=local_graph(); g.add((G.W1,RDF.type,G.MaintenanceWorkOrder)); g.add((G.W1,G.targets,G.S1))
    assert Grid(g).analyze()['households']==1200

def test_api():
    with TestClient(app) as c:
        assert c.get('/').status_code==200
        assert c.get('/api/health').json()['status']=='ok'
        assert len(c.get('/api/model').json()['classes'])>=15
        assert c.post('/api/analyze',json={'states':{'S1':'open'}}).json()['households']==1200
        assert c.post('/api/analyze',json={'states':{'bad':'open'}}).status_code==422
        assert c.post('/api/chat',json={'question':'S1断开后哪些用户失电？'}).json()['evidence']['households']==1200
        assert not c.post('/api/chat',json={'question':'写一首诗'}).json()['supported']
        assert c.post('/api/chat',json={'question':''}).status_code==422

def test_sparql_fetch_uses_named_graph(monkeypatch):
    import store, httpx
    monkeypatch.setenv('SPARQL_QUERY_URL','http://localhost:7200/repositories/test')
    observed=[]
    def handler(request):
        observed.append(request.content.decode())
        return httpx.Response(200,text=local_graph().serialize(format='turtle'))
    original=httpx.Client
    monkeypatch.setattr(store.httpx,'Client',lambda **kw: original(transport=httpx.MockTransport(handler),**kw))
    assert len(store.fetch())>0
    assert 'CONSTRUCT' in observed[0] and 'grid-demo' in observed[0]

def test_remote_error_no_silent_fallback(monkeypatch):
    import store
    monkeypatch.setenv('GRID_BACKEND','sparql'); grid.cache_clear()
    def fail(): raise ValueError('远程图为空')
    monkeypatch.setattr(store,'fetch',fail)
    with TestClient(app) as c: assert c.get('/api/health').status_code==422
    grid.cache_clear()

def test_neo4j_rdf_roundtrip():
    from neo4j_store import records,decode
    from rdflib.compare import isomorphic
    g=local_graph()
    assert isomorphic(g,decode(records(g)))
    assert len({r['key'] for r in records(g)})==len(g)

def test_neo4j_import_and_fetch_mock(monkeypatch):
    import neo4j_store as ns
    memory=[]; statements=[]
    class Result:
        def consume(self): pass
    class Driver:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def verify_connectivity(self): pass
        def session(self,**kw): return self
        def execute_write(self,fn): fn(self)
        def run(self,query,**kw):
            statements.append(query)
            if 'GridDemoTriple' in query: memory[:]=kw['rows']
            return Result()
        def execute_query(self,query,**kw):
            assert kw['scope']=='grid-demo-v1'
            return type('R',(),{'records':[{'t':r} for r in memory]})()
    monkeypatch.setattr(ns,'connection',lambda:Driver())
    assert ns.import_demo()==len(local_graph())
    assert len(ns.fetch())==len(local_graph())
    assert len(statements)==3
    assert all('DELETE' not in q and 'DROP' not in q for q in statements)

def test_neo4j_no_password(monkeypatch):
    from neo4j_store import connection
    monkeypatch.delenv('NEO4J_PASSWORD',raising=False)
    with pytest.raises(ValueError,match='NEO4J_PASSWORD'): connection()
