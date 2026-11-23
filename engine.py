from collections import deque
from pathlib import Path
from decimal import Decimal
from rdflib import Graph, Namespace, RDF, RDFS, OWL
from owlrl import DeductiveClosure, OWLRL_Semantics
G=Namespace('https://example.org/grid#')
BASE=Path(__file__).parent
RULES=[('R1','子类类型继承','OWL RL'),('R2','上下游传递','OWL RL'),('R3','电气连接对称','OWL RL'),('R4','开关断开或设备停运切断通路','拓扑'),('R5','从在役电源遍历可达设备，判定带电','拓扑'),('R6','全部供电配变失电才判定用户组失电','业务'),('R7','当前负荷大于额定容量判定过载','业务'),('R8','备用路径必须恢复全部目标失电配变','业务'),('R9','备用馈线剩余容量必须足够','业务'),('R10','转供后不能多电源并列或形成环网','业务'),('R11','故障设备及检修设备从有效拓扑移除','业务')]
def local_graph():
    g=Graph(); g.parse(BASE/'data/ontology.ttl'); g.parse(BASE/'data/demo.ttl'); return g

def short(u): return str(u).split('#')[-1]

class Grid:
    def __init__(self,g=None):
        self.raw=g if g is not None else local_graph()
        self.g=Graph()
        for t in self.raw: self.g.add(t)
        DeductiveClosure(OWLRL_Semantics).expand(self.g)
        self.equipment=set(self.g.subjects(RDF.type,G.ElectricalEquipment))
        self.switches=set(self.g.subjects(RDF.type,G.Switch))
        self.transformers=set(self.g.subjects(RDF.type,G.DistributionTransformer))
        self.customers=set(self.g.subjects(RDF.type,G.Customer))
        self.validate()
    def value(self,n,p): return self.raw.value(n,G[p])
    def number(self,n,p): return Decimal(str(self.value(n,p)))
    def validate(self):
        errors=[]
        for n in self.equipment:
            v=self.value(n,'inService')
            if v is None or v.toPython() not in (True,False) or not isinstance(v.toPython(),bool): errors.append(f'{short(n)}: inService 必须是布尔值')
        for n in self.switches:
            if str(self.value(n,'status')) not in ('open','closed'): errors.append(f'{short(n)}: 缺少有效开关状态')
        for n in self.transformers|set(self.g.subjects(RDF.type,G.Feeder)):
            for p in ['ratedCapacity','currentLoad']:
                try:
                    v=self.number(n,p)
                    if not v.is_finite() or v<0 or (p=='ratedCapacity' and v==0): raise ValueError()
                except Exception: errors.append(f'{short(n)}: {p} 必须为有效容量(kVA)')
        for n in self.customers:
            try:
                v=self.number(n,'households')
                if not v.is_finite() or v<0 or v!=int(v): raise ValueError()
            except Exception: errors.append(f'{short(n)}: households 必须为非负整数')
            if not any(self.raw.subjects(G.supplies,n)): errors.append(f'{short(n)}: 缺少供电配变')
        if self.equipment & self.customers: errors.append('设备与用户类型互斥冲突')
        if errors: raise ValueError('; '.join(errors))
    def topology(self,states=None,blocked=()):
        states=states or {}; blocked=set(blocked)
        for id,state in states.items():
            if G[id] not in self.switches or state not in ('open','closed'): raise ValueError(f'无效开关或状态: {id}')
        for id in blocked:
            if G[id] not in self.equipment: raise ValueError(f'未知设备: {id}')
        blocked={G[id] for id in blocked}
        blocked.update(n for n in self.equipment if self.value(n,'inService').toPython() is False)
        blocked.update(self.raw.subjects(G.hasFault,None))
        for order in self.g.subjects(RDF.type,G.MaintenanceWorkOrder): blocked.update(self.raw.objects(order,G.targets))
        blocked.update(n for n in self.switches if states.get(short(n),str(self.value(n,'status')))=='open')
        adj={n:set() for n in self.equipment if n not in blocked}
        for a,b in self.raw.subject_objects(G.connectedTo):
            if a in adj and b in adj: adj[a].add(b); adj[b].add(a)
        sources={n for n in adj if self.value(n,'isSource') is not None and self.value(n,'isSource').toPython() is True}
        return adj,sources
    def analyze(self,states=None,blocked=()):
        adj,sources=self.topology(states,blocked); reached=set(); paths={}; q=deque()
        for n in sorted(sources): reached.add(n); paths[n]=[short(n)]; q.append(n)
        while q:
            a=q.popleft()
            for b in sorted(adj[a]):
                if b not in reached: reached.add(b); paths[b]=paths[a]+[short(b)]; q.append(b)
        lost=self.transformers-reached
        customers={n for n in self.customers if not (set(self.raw.subjects(G.supplies,n)) & reached)}
        overloaded=[{'id':short(n),'load_kva':float(self.number(n,'currentLoad')),'capacity_kva':float(self.number(n,'ratedCapacity'))} for n in sorted(self.transformers) if self.number(n,'currentLoad')>self.number(n,'ratedCapacity')]
        return {'outage_transformers':sorted(map(short,lost)),'outage_customers':sorted(map(short,customers)),'households':sum(int(self.number(n,'households')) for n in customers),'energized':sorted(map(short,reached)),'paths':{short(n):p for n,p in paths.items()},'overloads':overloaded,'evidence':['R4/R5: 在役电源通过闭合开关及可用设备进行连通性遍历','R6: 用户全部供电路径失效才计为失电','R7: currentLoad > ratedCapacity'],'data_source':'synthetic demo'}
    def transfer(self,tie='L1',target='X',backup='Y',states=None,blocked=()):
        states=dict(states or {}); blocked=list(blocked)
        if (G[tie],RDF.type,G.TieSwitch) not in self.g: raise ValueError('联络开关不存在')
        if (G[target],G.backupFeeder,G[backup]) not in self.raw: raise ValueError('未配置此备用馈线关系')
        before=self.analyze(states,blocked); after_states={**states,tie:'closed'}; after=self.analyze(after_states,blocked)
        lost={G[n] for n in before['outage_transformers'] if self.value(G[n],'belongsTo')==G[target]}
        required=sum((self.number(n,'currentLoad') for n in lost),Decimal(0))
        spare=self.number(G[backup],'ratedCapacity')-self.number(G[backup],'currentLoad')
        reasons=[]
        if not lost: reasons.append('目标馈线没有待恢复的失电配变')
        if not {short(n) for n in lost}.issubset(set(after['energized'])): reasons.append('闭合联络开关后仍有目标配变失电')
        if required>spare: reasons.append('备用馈线容量不足')
        adj,sources=self.topology(after_states,blocked); visited=set()
        for node in adj:
            if node in visited: continue
            comp=set(); q=[node]
            while q:
                n=q.pop()
                if n in comp: continue
                comp.add(n); q.extend(adj[n]-comp)
            visited|=comp
            if comp & {G[tie]}:
                if G[backup] not in comp or G[backup] not in sources: reasons.append('联络路径未连接指定备用电源')
                if len(comp & sources)>1: reasons.append('会形成多电源并列')
                if sum(len(adj[n]) for n in comp)//2>=len(comp): reasons.append('会形成环网')
        if G[tie] not in adj: reasons.append('联络开关停运、故障或检修中')
        if any(short(n) in after['energized'] and self.number(n,'currentLoad')>self.number(n,'ratedCapacity') for n in lost): reasons.append('待转供配变自身已过载')
        return {'screening_passed':not reasons,'operationally_approved':False,'tie':tie,'target':target,'backup':backup,'required_kva':float(required),'spare_kva':float(spare),'reasons':reasons,'after':after,'evidence':['R8: 目标配变全部恢复','R9: 备用馈线容量校验','R10: 多电源与环网检查','R11: 故障及检修隔离'],'limitation':'仅进行静态拓扑与kVA容量初筛；未校验潮流、电压、线路载流量、保护配合、同期及调度规程，不构成可执行操作指令。'}
    def view(self):
        nodes=[{'id':short(n),'label':str(self.value(n,'label') or short(n)),'types':sorted(short(t) for t in self.g.objects(n,RDF.type) if str(t).startswith(str(G)))} for n in sorted(self.equipment|self.customers)]
        edges=[{'source':short(a),'target':short(b),'relation':short(p)} for p in [G.connectedTo,G.supplies] for a,b in self.raw.subject_objects(p)]
        classes=sorted(short(n) for n in self.raw.subjects(RDF.type,OWL.Class))
        hierarchy=[{'source':short(a),'target':short(b),'relation':'subClassOf'} for a,b in self.raw.subject_objects(RDFS.subClassOf)]
        return {'nodes':nodes,'edges':edges,'classes':classes,'hierarchy':hierarchy,'rules':[{'id':a,'description':b,'engine':c} for a,b,c in RULES]}
