# 配电网本体与知识推理 Demo

Python 3.11+；FastAPI + RDFLib + OWL RL + 无外部 CDN 的浏览器页面。

## Windows PowerShell 启动

在解压后的 grid-demo 目录执行：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe generate.py
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

浏览器访问 http://127.0.0.1:8000 ，接口说明 http://127.0.0.1:8000/docs 。不必激活虚拟环境，不修改执行策略。默认 local 模式不依赖任何数据库。

Linux/macOS 可使用 python3 -m venv .venv，后续改用 .venv/bin/python。

## 复用现有 Neo4j（推荐）

用户已确认现有 MySQL、Redis、MinIO、Neo4j、ES；本 Demo 使用 Neo4j 作为可选持久化，其余数据库暂不需要。默认 local 仍可独立运行。Neo4j 是属性图，不会自行执行 OWL 语义，本体推理由 Python OWL RL 完成。

确认实际地址、版本、用户名及数据库名后，在本机设置（下面为占位示例，不表示已连接）：

```powershell
$env:NEO4J_URI='bolt://127.0.0.1:7687'
$env:NEO4J_USERNAME='neo4j'
$env:NEO4J_DATABASE='neo4j'
# 使用 PowerShell 安全输入；不在命令历史写明文密码
$credential = Get-Credential -UserName $env:NEO4J_USERNAME -Message '输入本机 Neo4j 凭据'
$env:NEO4J_PASSWORD=$credential.GetNetworkCredential().Password
.\.venv\Scripts\python.exe neo4j_store.py import-demo --confirm-demo-write
.\.venv\Scripts\python.exe neo4j_store.py check
$env:GRID_BACKEND='neo4j'
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

支持官方驱动 Bolt 连接，目标 Neo4j 5.x/2025+；未知旧版本需要先验证。导入使用一个事务，参数化 Cypher，只 MERGE 带 GridDemoTriple/GridDemoEntity 标签与 scope=grid-demo-v1 的独立模拟数据，不删除、清空或覆盖其他标签的数据；不创建全库约束。请使用测试数据库，且不要并发执行导入。重复串行导入不会重复创建三元组。模拟图为持久化事实，页面场景变化不回写。

Neo4j Browser 中查看实例关系：

```cypher
MATCH (a:GridDemoEntity {scope:'grid-demo-v1'})-[r:GRID_DEMO_RELATION]->(b:GridDemoEntity)
RETURN a,r,b;
```

GridDemoTriple 保存完整 RDF 三元组及字面量类型；GridDemoEntity/GRID_DEMO_RELATION 是只供可视化的投影。修改投影不会改变分析输入，修改事实应更新对应三元组并重启应用。第一版不提供数据编辑界面。

## 可选 SPARQL 数据库接口（现有 Neo4j 不需要）

此项目不提供数据库 Compose，不会替换现有服务。先确认数据库类型及仓库名：SPARQL 适配器适用于提供 SPARQL 1.1 CONSTRUCT / Update 接口的数据库；MySQL、PostgreSQL、Neo4j 不能直接使用此适配器。

若确认是 GraphDB，先在已有实例创建专用测试 Repository，以下 grid-demo 仅为示例仓库名：

```powershell
$env:SPARQL_QUERY_URL='http://127.0.0.1:7200/repositories/grid-demo'
$env:SPARQL_UPDATE_URL='http://127.0.0.1:7200/repositories/grid-demo/statements'
# 若已配置 bearer 鉴权，令牌只放在本机环境变量 SPARQL_BEARER_TOKEN
# 显式向专用 Demo 命名图追加测试数据；不清空现有图。
.\.venv\Scripts\python.exe store.py import-demo --confirm-demo-write
.\.venv\Scripts\python.exe store.py check
$env:GRID_BACKEND='sparql'
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

仅支持可选 Bearer 令牌；其他鉴权方式需适配。查询限定到 https://example.org/grid-demo 命名图。不同产品的 query / update URL 要按该产品配置；不根据 URL 猜测接口。配置示例见 .env.example（不自动加载）。宿主机运行服务时 localhost 指宿主机；如果以后将应用也放入容器，需改用容器网络服务名或正确的宿主机地址。

后端首次请求读取远程快照，修改数据库后重启应用刷新；场景分析均为无副作用的内存计算。远程读取失败会报错，没有静默降级。

## 5 个验收问题

| 问题 | 场景 | 预期结果 |
|---|---|---|
| S1 断开后哪些用户失电？ | S1=open，L1=open | 配变 A/B；用户组 U1/U2；1200 户 |
| 哪些配变过载？ | 基准场景 | C，500 > 400 kVA |
| S1 断开后能否转供到 Y？ | S1=open，L1=open | 需求 700、余量 1500 kVA；闭合 L1 后恢复；仅初筛通过 |
| S1 是否属于电力设备？ | OWL RL | 是，通过 SectionalizingSwitch → Switch → ElectricalEquipment |
| 哪些用户位于 S1 下游？ | 语义图 SPARQL | U1/U2；不等同于实时失电结论 |

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## 文件与能力

- docs/材料文字提取.md：材料全文整理。
- docs/设计说明.md：本体与数据库区别、设计取舍、能力边界。
- data/ontology.ttl：20 个类及属性，可在 Protégé 中打开。
- data/demo.ttl：模拟实例数据。
- engine.py：OWL RL + 拓扑 + 业务规则；11 条规则可从页面查看。
- app.py：分析、转供、对话、模型接口；没有任意 SPARQL 执行入口。
- neo4j_store.py：现有 Neo4j 的持久化、读取和可视化投影。
- store.py：独立命名图读取及显式 Demo 导入。
- static/index.html：实例拓扑、本体继承、场景和对话。
- tests/test_demo.py：验收与边界测试，远程接口使用 MockTransport；真实 Docker 尚未联调。

对话是有限意图工具路由，不依赖 LLM API；真实模型接入、完整 CIM 模型、SHACL 校验、多时态数据、工程潮流和生产权限审计不在本版实现范围。缺失或无效容量和开关状态会拒绝分析，而不会假定为零或闭合。

本地只绑定 127.0.0.1，Demo 没有多用户鉴权，不应直接暴露到公网。转供结果永远不是调度指令。

参考：
- https://rdflib.readthedocs.io/en/latest/intro_to_parsing/
- https://rdflib.readthedocs.io/en/latest/intro_to_sparql/
- https://graphdb.ontotext.com/documentation/11.4/sparql-queries.html

Neo4j 官方参考：https://neo4j.com/docs/python-manual/current/connect/ 、https://neo4j.com/docs/python-manual/current/query-simple/
