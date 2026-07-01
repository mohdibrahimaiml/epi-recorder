from __future__ import annotations
from pathlib import Path;import json
from datetime import datetime,timezone
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from epi_core.annex_schemas import *
from epi_core.keys import KeyManager
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

console=Console()
annex_app=typer.Typer(help="Annex IV compliance artifacts")
D="artifacts/annex_iv"
SEC={"1":"System Description","2":"Development Process","3":"Monitoring and Control","4":"Performance Metrics","5":"Risk Management","6":"Lifecycle Changes","7":"Applied Standards","8":"EU Declaration of Conformity","9":"Post-Market Monitoring"}
CLS={"1":Section01System,"2":Section02Development,"3":Section03Monitoring,"4":Section04Metrics,"5":Section05RiskManagement,"6":Section06Lifecycle,"7":Section07Standards,"8":Section08Declaration,"9":Section09PostMarket}

def _canon(data):ac={k:v for k,v in data.get("approval",{}).items() if k!="signature"};cd=dict(data);cd["approval"]=ac;cd.pop("signature",None);return json.dumps(cd,sort_keys=True,separators=(",",":"),default=str)
def _key(n):km=KeyManager();km.has_key(n)or km.generate_keypair(n);return km.load_private_key(n)
def _pub(n):return KeyManager().load_public_key(n)

@annex_app.command()
def init(force:bool=False,out:Path=Path(".")):
    d=out/D;d.mkdir(exist_ok=True,parents=True)
    for n,t in SEC.items():
        f=d/f"section-0{n}.json"
        if f.exists()and not force:console.print(f"  SKIP {f.name}");continue
        m=CLS[n]().model_dump(mode="json")
        f.write_text(json.dumps(m,indent=2,default=str))
        console.print(f"  OK Section {n}")
    console.print(Panel(f"Generated {len(SEC)} templates",title="Annex IV Init"))

@annex_app.command()
def validate(dir:Path=Path(".")):
    b=dir/D
    if not b.exists():console.print("[red]No artifacts/annex_iv/ found[/]");raise typer.Exit(1)
    p,f=0,0
    for n,t in SEC.items():
        fp=b/f"section-0{n}.json"
        if not fp.exists():console.print(f"  MISSING {n}");f+=1;continue
        try:d=json.loads(fp.read_text());CLS[n](**d);console.print(f"  PASS {n}");p+=1
        except Exception as e:console.print(f"  FAIL {n}:{e}");f+=1
    console.print(Panel(f"{p}/{len(SEC)} pass,{f} fail",title="Validate"))
    if f:raise typer.Exit(1)
@annex_app.command()
def status(dir:Path=Path(".")):
    b=dir/D;t=Table(title="Annex IV Status");t.add_column("Sec");t.add_column("Section");t.add_column("Status");t.add_column("Approved")
    for n,s in SEC.items():
        f=b/f"section-0{n}.json"
        if not f.exists():t.add_row(n,s,"[red]MISSING[/]","-");continue
        d=json.loads(f.read_text());st=d.get("meta",{}).get("status","draft");ap=d.get("approval",{}).get("signed_by","-")or"-"
        co={"missing":"red","draft":"yellow","complete":"green","approved":"green"}.get(st,"yellow")
        t.add_row(n,s,f"[{co}]{st.upper()}[/]",ap)
    console.print(t)

@annex_app.command()
def compile(dir:Path=Path("."),out:Path=Path(".")):
    b=dir/D;assert b.exists(),"Run init first"
    ss=[];pop=0;app=0
    for n,t in SEC.items():
        f=b/f"section-0{n}.json"
        if not f.exists():ss.append({"section":n,"title":t,"status":"missing"});continue
        d=json.loads(f.read_text());st=d.get("meta",{}).get("status","draft");ap=d.get("approval",{})
        if st in ("complete","approved"):pop+=1
        if st=="approved":app+=1
        ss.append({"section":n,"title":t,"status":st,"approved_by":ap.get("signed_by","-"),"approved_at":ap.get("signed_at","")})
    sm={"system_name":"","system_version":"","generated_at":datetime.now(timezone.utc).isoformat(),"sections":ss,"overall_completion_pct":round(pop*100/9,1),"approved_sections":app,"total_sections":9}
    op=out/D/"compliance-summary.json";op.parent.mkdir(parents=True,exist_ok=True);op.write_text(json.dumps(sm,indent=2))
    console.print(Panel(f"{pop}/9 complete,{app}/9 approved",title="Annex IV Compile"))
@annex_app.command()
def sign(sec:str=typer.Argument(...,help="Section 1-9 or all"),key_name:str="annex",dir:Path=Path("."),officer:str=""):
    b=dir/D;assert b.exists(),"Run init first"
    pk=_key(key_name);ss=list(SEC.keys())if sec=="all"else[sec]
    for s in ss:
        assert s in SEC,f"Invalid {s}";f=b/f"section-0{s}.json";assert f.exists()
        d=json.loads(f.read_text());a=d.setdefault("approval",{})
        a["signed_by"]=officer or f"epi:key:{key_name}";a["signed_at"]=datetime.now(timezone.utc).isoformat()
        c=_canon(d);sg=pk.sign(c.encode("utf-8"));a["signature"]=f"ed25519:{key_name}:{sg.hex()}"
        f.write_text(json.dumps(d,indent=2,default=str))
        console.print(f"  SIGNED Section {s}")
    console.print(Panel(f"Signed {len(ss)} sections",title="Annex IV Sign"))

@annex_app.command()
def verify(sec:str=typer.Argument("all"),dir:Path=Path(".")):
    b=dir/D;ss=list(SEC.keys())if sec=="all"else[sec];pg=0;fl=0
    for s in ss:
        f=b/f"section-0{s}.json"
        if not f.exists():console.print(f"  MISSING Section {s}");fl+=1;continue
        d=json.loads(f.read_text());sg=d.get("approval",{}).get("signature","")
        if not sg:console.print(f"  UNSIGNED Section {s}");continue
        try:
            p=sg.split(":",2);pb=_pub(p[1]);c=_canon(d);ed=Ed25519PublicKey.from_public_bytes(pb)
            ed.verify(bytes.fromhex(p[2]),c.encode("utf-8"))
            console.print(f"  VALID Section {s} (key:{p[1]})");pg+=1
        except Exception as ex:console.print(f"  INVALID Section {s}:{ex}");fl+=1
    console.print(Panel(f"{pg} valid,{fl} invalid",title="Verify"))
    if fl:raise typer.Exit(1)

@annex_app.command()
def report(dir:Path=Path("."),out:Path=Path(".")):
    from epi_core.annex_report_template import REPORT_HTML
    b=dir/D;assert b.exists(),"Run init first"
    rows="";tp=0.0;A=chr(60);B=chr(62)
    for n,t in SEC.items():
        f=b/f"section-0{n}.json"
        if not f.exists():st="missing";by="-"
        else:d=json.loads(f.read_text());st=d.get("meta",{}).get("status","draft");by=d.get("approval",{}).get("signed_by","-")or"-";tp+=100.0/9 if st in("complete","approved")else 0
        co={"missing":"#e74c3c","draft":"#f39c12","complete":"#2ecc71","approved":"#27ae60"}.get(st,"#95a5a6")
        rows+=A+"tr"+B+A+"td"+B+n+A+"/td"+B+A+"td"+B+t+A+"/td"+B+A+"td style=color:"+co+";font-weight:600"+B+st.upper()+A+"/td"+B+A+"td"+B+by+A+"/td"+B+A+"/tr"+B
    ts=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html=REPORT_HTML.replace("TIMESTAMP",ts).replace("PCT",f"{tp:.0f}").replace("ROWS",rows)
    op=out.resolve();op=op/"annex-iv-compliance-report.html"if op.is_dir()else op
    op.write_text(html,encoding="utf-8");console.print(f"Report: {op}")