# PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.
import numpy as np
from scipy.stats import norm
rng=np.random.default_rng(20261020); n=400000
# grid shocks: super, stall, copper, GSI, recession, execution (red-geo set)
names=['super','stall','copper','gsi','recess','exec']
P12=np.array([.15,.20,.20,.12,.15,.08]); P24=np.array([.20,.25,.25,.22,.25,.15])
C=np.eye(6)
def s(i,j,v): C[i,j]=C[j,i]=v
s(0,1,-.4); s(0,4,-.4); s(1,4,.4); s(2,4,-.3); s(1,2,0); s(5,1,.2)  # gsi independent
for P,lab in [(P12,'12m'),(P24,'24m')]:
    z=rng.multivariate_normal(np.zeros(6),C,n); on=z<norm.ppf(P)
    neg=on[:,1:]
    print(lab,'P(no shock)',round((~on.any(1)).mean(),3),'P(no neg shock)',round((~neg.any(1)).mean(),3),
          'P(>=2 neg)',round((neg.sum(1)>=2).mean(),3),'P(recess&copper)',round((on[:,4]&on[:,2]).mean(),3))
# original grid: independent vs rho .63 (what P(>=2 neg) looks like)
Pt=np.array([.15,.20,.20,.25,.15]); k=5
for rho in [0,.63]:
    Ct=np.full((k,k),rho); np.fill_diagonal(Ct,1); Ct[0,1:]=Ct[1:,0]=-rho
    w=np.linalg.eigvalsh(Ct).min()
    z=rng.multivariate_normal(np.zeros(k),Ct,n,check_valid='ignore'); on=z<norm.ppf(Pt)
    print('original rho',rho,'min eig',round(w,3),'P(no shock)',round((~on.any(1)).mean(),3),'P(>=2 neg)',round((on[:,1:].sum(1)>=2).mean(),3),'P(recess&copper)',round((on[:,4]&on[:,2]).mean(),3))
# semis original: pure base
print('semis original 12m pure base (no overlay):',round(45/94*0.7*0.8,3),' 24m:',round(30/80*0.55*0.7,3))
# red-geo semis 12m: states base, boom, nand, aipause, taiwan_block ; overlays export(US-China), china-japan, quarantine, yen, onshoring(not with rapidus slip)
st12={'base':.455,'boom':.22,'nand':.15,'aipause':.10,'taiwan':.025}; st24={'base':.25,'boom':.17,'nand':.30,'aipause':.22,'taiwan':.06}
for st,lab,ov in [(st12,'12m',[.30,.15,.05,.15,.20]),(st24,'24m',[.45,.25,.10,.20,.30])]:
    print(lab,'states sum',round(sum(st.values()),3),'pure base',round(st['base']*np.prod([1-x for x in ov]),3))
