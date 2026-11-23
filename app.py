import os
from pathlib import Path
from functools import lru_cache
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from engine import Grid
import store
from neo4j.exceptions import Neo4jError, DriverError
BASE=Path(__file__).parent
app=FastAPI(title='配电网本体与推理 Demo',version='0.1.0')
class Scenario(BaseModel):
    states:dict[str,str]=Field(default_factory=dict)
    blocked:list[str]=Field(default_factory=list)
class Transfer(Scenario):
    tie:str='L1'
    target:str='X'
    backup:str='Y'
class Question(Scenario):
    question:str=Field(min_length=1,max_length=500)
@lru_cache(maxsize=1)
def grid():
    mode=os.getenv('GRID_BACKEND','local')
    if mode not in ('local','sparql','neo4j'): raise ValueError('GRID_BACKEND 只能是 local、neo4j 或 sparql')
    if mode=='neo4j':
        import neo4j_store
        return Grid(neo4j_store.fetch())
    return Grid(store.fetch()) if mode=='sparql' else Grid()
def run(fn):
    try: return fn(grid())
    except ValueError as e: raise HTTPException(422,str(e)) from e
    except (Neo4jError, DriverError) as e: raise HTTPException(503,'Neo4j 连接或查询失败，请检查本机连接配置及独立 Demo 数据。') from e
    except httpx.HTTPError as e: raise HTTPException(503,'SPARQL 数据库不可达或拒绝请求；请检查本机配置。') from e
@app.get('/')
def index(): return FileResponse(BASE/'static/index.html')
@app.get('/api/health')
def health(): return run(lambda g:{'status':'ok','backend':os.getenv('GRID_BACKEND','local'),'raw_triples':len(g.raw),'inferred_triples':len(g.g),'snapshot':'进程首次读取时加载；修改远程数据后重启刷新'})
@app.get('/api/model')
def model(): return run(lambda g:g.view())
@app.post('/api/analyze')
def analyze(body:Scenario): return run(lambda g:g.analyze(body.states,body.blocked))
@app.post('/api/transfer')
def transfer(body:Transfer): return run(lambda g:g.transfer(body.tie,body.target,body.backup,body.states,body.blocked))
@app.post('/api/chat')
def chat(body:Question):
    def answer(g):
        q=body.question.strip(); states=dict(body.states)
        if 'S1' in q.upper() and any(w in q for w in ['断开','停电','失电']): states['S1']='open'
        if any(w in q for w in ['转供','转移','备用','合闸']):
            result=g.transfer(states=states,blocked=body.blocked)
            message=('容量与拓扑初筛通过。' if result['screening_passed'] else '初筛未通过：'+'；'.join(result['reasons'])+'。')+result['limitation']
        elif any(w in q for w in ['过载','停电','失电','影响','下游']):
            result=g.analyze(states,body.blocked)
            message=f"失电配变：{', '.join(result['outage_transformers']) or '无'}；失电用户组：{', '.join(result['outage_customers']) or '无'}；共 {result['households']} 户。过载配变：{', '.join(x['id'] for x in result['overloads']) or '无'}。"
        elif any(w in q for w in ['规则','本体','类']):
            result=g.view(); message=f"本体包含 {len(result['classes'])} 个类，{len(result['rules'])} 条语义或业务规则。"
        else: return {'answer':'此版本使用确定性意图路由，不调用大语言模型。支持失电影响、过载、转供及本体规则问题。','supported':False,'mode':'deterministic tool router'}
        return {'answer':message,'evidence':result,'supported':True,'mode':'deterministic tool router'}
    return run(answer)
