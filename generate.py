"""Generate the OWL vocabulary and a separate, explicitly synthetic dataset."""
from pathlib import Path
from rdflib import Graph, Namespace, Literal, RDF, RDFS, OWL, XSD
BASE=Path(__file__).parent
G=Namespace('https://example.org/grid#')
def build():
    g=Graph(); g.bind('grid',G); g.bind('owl',OWL)
    g.add((G.ontology,RDF.type,OWL.Ontology))
    classes={'GridEntity':None,'ElectricalEquipment':'GridEntity','Substation':'ElectricalEquipment','Feeder':'ElectricalEquipment','Busbar':'ElectricalEquipment','LineSegment':'ElectricalEquipment','Switch':'ElectricalEquipment','SectionalizingSwitch':'Switch','TieSwitch':'Switch','DistributionTransformer':'ElectricalEquipment','Customer':'GridEntity','ResidentialCustomer':'Customer','IndustrialCustomer':'Customer','GridEvent':'GridEntity','Fault':'GridEvent','Outage':'GridEvent','OverloadEvent':'GridEvent','BusinessObject':'GridEntity','MaintenanceWorkOrder':'BusinessObject','SwitchingPlan':'BusinessObject'}
    for cls,parent in classes.items():
        g.add((G[cls],RDF.type,OWL.Class))
        if parent: g.add((G[cls],RDFS.subClassOf,G[parent]))
    objects={'connectedTo':('ElectricalEquipment','ElectricalEquipment'),'downstreamOf':('ElectricalEquipment','ElectricalEquipment'),'supplies':('DistributionTransformer','Customer'),'belongsTo':('ElectricalEquipment','Feeder'),'hasFault':('ElectricalEquipment','Fault'),'targets':('MaintenanceWorkOrder','ElectricalEquipment'),'backupFeeder':('Feeder','Feeder')}
    for name,(domain,ran) in objects.items():
        g.add((G[name],RDF.type,OWL.ObjectProperty)); g.add((G[name],RDFS.domain,G[domain])); g.add((G[name],RDFS.range,G[ran]))
    g.add((G.connectedTo,RDF.type,OWL.SymmetricProperty)); g.add((G.downstreamOf,RDF.type,OWL.TransitiveProperty))
    g.add((G.Customer,OWL.disjointWith,G.ElectricalEquipment))
    props={'status':XSD.string,'ratedCapacity':XSD.decimal,'currentLoad':XSD.decimal,'households':XSD.integer,'inService':XSD.boolean,'isSource':XSD.boolean}
    for name,typ in props.items():
        g.add((G[name],RDF.type,OWL.DatatypeProperty)); g.add((G[name],RDFS.domain,G.GridEntity)); g.add((G[name],RDFS.range,typ))
    # Every class inherits data property label and the object property relatedTo.
    for name,typ,ran in [('label',OWL.DatatypeProperty,XSD.string),('relatedTo',OWL.ObjectProperty,G.GridEntity)]:
        g.add((G[name],RDF.type,typ)); g.add((G[name],RDFS.domain,G.GridEntity)); g.add((G[name],RDFS.range,ran))
    g.serialize(BASE/'data/ontology.ttl',format='turtle')
    d=Graph(); d.bind('grid',G)
    devices=[('X','Feeder','馈线 X'),('Y','Feeder','馈线 Y'),('S1','SectionalizingSwitch','分段开关 S1'),('L1','TieSwitch','联络开关 L1'),('A','DistributionTransformer','配变 A'),('B','DistributionTransformer','配变 B'),('C','DistributionTransformer','配变 C')]
    for id,cls,label in devices:
        d.add((G[id],RDF.type,G[cls])); d.add((G[id],G.label,Literal(label))); d.add((G[id],G.inService,Literal(True)))
    for src,dst in [('X','S1'),('S1','A'),('A','B'),('Y','L1'),('L1','B'),('Y','C')]: d.add((G[src],G.connectedTo,G[dst]))
    for id in ['X','Y']: d.add((G[id],G.isSource,Literal(True)))
    for id,state in [('S1','closed'),('L1','open')]: d.add((G[id],G.status,Literal(state)))
    for id,capacity,load in [('X',2000,700),('Y',2000,500),('A',630,400),('B',400,300),('C',400,500)]:
        for p,v in [('ratedCapacity',capacity),('currentLoad',load)]: d.add((G[id],G[p],Literal(v,datatype=XSD.decimal)))
    for id,feeder in [('A','X'),('B','X'),('C','Y')]: d.add((G[id],G.belongsTo,G[feeder]))
    for src,dst in [('A','S1'),('B','A'),('S1','X'),('C','Y')]: d.add((G[src],G.downstreamOf,G[dst]))
    d.add((G.X,G.backupFeeder,G.Y))
    for id,tr,n,cls in [('U1','A',700,'ResidentialCustomer'),('U2','B',500,'ResidentialCustomer'),('U3','C',100,'IndustrialCustomer')]:
        d.add((G[id],RDF.type,G[cls])); d.add((G[id],G.label,Literal('用户组 '+id))); d.add((G[id],G.households,Literal(n))); d.add((G[tr],G.supplies,G[id]))
    d.serialize(BASE/'data/demo.ttl',format='turtle')
if __name__=='__main__': build()
