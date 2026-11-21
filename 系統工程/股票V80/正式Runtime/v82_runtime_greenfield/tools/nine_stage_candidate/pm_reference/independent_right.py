"""Isolated implementation of approved TECH R1..R10/off_low definitions.
No M maturity predicate is used in R confirmation. Source: v1.0 TECH.
This is candidate research, not a replacement of the production producer.
"""
from decimal import Decimal as D,localcontext,ROUND_HALF_EVEN
from . import candidate as b

def produce(rows):
 with localcontext() as ctx:
  ctx.prec=50;ctx.rounding=ROUND_HALF_EVEN
  return _produce(rows)

def _produce(rows):
 fs=b.features(rows);n=b.n
 def seq(key):return [D(str(r[key])) if r.get(key) is not None else None for r in rows]
 c,h,l,v=(seq(x) for x in ('Close','High','Low','Volume'))
 _,k,d=n.kd(h,l,c);_,_,dif,dea,hist=n.macd(c);_,_,rsi=n.rsi(c);_,_,emv=n.emv(h,l,v)
 ma20=n.sma(c,20);vma=n.sma(v,20)
 def at(xs,i):return xs[i] if 0<=i<len(xs) else None
 def cmp(xs,i,op,ys,j):return b.compare(at(xs,i),op,at(ys,j))
 def mx(xs,i,j):
  w=xs[i:j+1] if i>=0 else []
  return max(w) if len(w)==j-i+1 and w and None not in w else None
 def pivots(xs,side):
  result=[]
  for i in range(2,len(xs)-2):
   w=xs[i-2:i]+xs[i+1:i+3]
   if xs[i] is not None and None not in w and (xs[i]>max(w) if side=='H' else xs[i]<min(w)):
    result.append((i,xs[i]))
  return result
 ph,pl=pivots(h,'H'),pivots(l,'L')
 def latest(ps,s,w=20):
  q=[x for x in ps if x[0]+2<=s and s-w<=x[0]<=s]
  return q[-1] if q else None
 def cross(i):
  p=latest(ph,i-1)
  return (None,None) if p is None else (b.AND(b.compare(at(c,i-1),'<=',p[1]),b.compare(at(c,i),'>',p[1])),p)
 output=[]
 for t,f in enumerate(fs):
  p=t-1
  lows=[x for x in pl if x[0]+2<=t]
  higher=None
  if len(lows)>=2:
   a,z=lows[-2:]
   if t-a[0]<=60 and t-z[0]<=20:higher=z[1]>a[1]
  golden=b.AND(cmp(k,p,'<=',d,p),cmp(k,t,'>',d,t))
  r3=b.OR(b.AND(b.compare(at(hist,t),'<',0),b.compare(at(hist,p),'<',0),cmp(hist,t,'>',hist,p)),
          b.AND(b.compare(at(hist,p),'<=',0),b.compare(at(hist,t),'>',0)))
  near=b.AND(b.compare(at(rsi,t),'>=',45),b.compare(at(rsi,t),'<=',55))
  rise=b.AND(b.compare(at(rsi,t-3),'>=',30),b.compare(at(rsi,t),'<=',50),
    cmp(rsi,t-3,'<',rsi,t-2),cmp(rsi,t-2,'<',rsi,p),cmp(rsi,p,'<',rsi,t))
  r8=None;hs=[x for x in ph if x[0]+2<=p]
  if len(hs)>=2:
   a,z=hs[-2:]
   if p-a[0]<=60 and z[0]-a[0]>=5 and z[1]<a[1]:
    def line(i):return a[1]+(z[1]-a[1])*D(i-a[0])/D(z[0]-a[0])
    untouched=b.AND(*(b.compare(at(c,i),'<=',line(i)) for i in range(z[0]+2,t)))
    ratio=None if at(vma,p) in (None,D(0)) or at(v,t) is None else v[t]/vma[p]
    r8=b.AND(untouched,b.compare(at(c,p),'<=',line(p)),b.compare(at(c,t),'>',line(t)),b.compare(ratio,'>=','1.5'))
  r9,_=cross(t);retest=[]
  if t>=34:
   for event in range(t-10,t):
    parent,ref=cross(event)
    if parent is None:retest.append(None);continue
    if not parent:continue
    level=ref[1];touch=None;vote=None
    for i in range(event+1,t+1):
     if any(at(x,i) is None for x in (c,h,l)) or at(c,i-1) is None:vote=None;break
     if c[i]<D('.99')*level:vote=False;break
     if touch is None and l[i]<=D('1.005')*level and h[i]>=D('.995')*level:touch=i
     if touch is not None and i<=min(touch+2,event+10) and c[i]>=level and c[i]>c[i-1]:vote=i==t;break
     if i==event+10 or touch is not None and i==touch+2:vote=False;break
    retest.append(vote)
   r10=b.OR(*retest)
  else:r10=None
  rs=[higher,golden,r3,cmp(dif,t,'>',dif,p),b.AND(b.compare(at(emv,p),'<=',0),b.compare(at(emv,t),'>',0)),
      b.OR(near,rise),b.AND(cmp(c,p,'<=',ma20,p),cmp(c,t,'>',ma20,t)),r8,r9,r10]
  low=latest(pl,t)
  off=b.compare(at(c,t),'>=',None if low is None else low[1]*D('1.01'))
  record=dict(f);record.update(R=rs,R_count=sum(x is True for x in rs),R_unknown=sum(x is None for x in rs),
    OffLow=off,R_votes_ok=b.votes(rs,3),R_ok=b.AND(off,b.votes(rs,3)))
  output.append(record)
 return output
